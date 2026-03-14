"""Unified bilingual dictionary lookup across multiple lexica."""

import json
import os
import re
import subprocess
import unicodedata
from collections import defaultdict
from pathlib import Path

import httpx

from backend.db import get_cache, set_cache
from backend.models.dictionary import DictionaryEntry, DictionarySense
from backend.services.transliterate import transliterate

DATA_DIR = Path(__file__).parent.parent / "data"
LSJ_PATH = DATA_DIR / "lsj-shortdefs.json"
LSJ_FULL_PATH = DATA_DIR / "dictionaries" / "lsj-full.json"
DICT_DIR = DATA_DIR / "dictionaries"

SOURCE_PRIORITY = [
    "lsj",
    "middle-liddell",
    "autenrieth",
    "slater",
]
MAX_LONG_DEF_CHARS = 100000
LOGEION_DETAIL_URL = "https://anastrophe.uchicago.edu/logeion-api/detail"
LOGEION_TIMEOUT_SECONDS = 12.0
LOGEION_CACHE_PREFIX = "logeion:detail:v1:"
LSJ_FULL_S3_URI = os.getenv("LSJ_FULL_S3_URI", "s3://ancientgreek/dictionaries/lsj-full.json")
BLOCKED_LOCAL_SOURCES = {"lewis"}
LATIN_LIVE_DICO_NAMES = {
    "LewisShort",
    "Lewis",
    "Georges",
    "DMLBS",
    "Gaffiot 2016",
    "LaNe",
    "Latino-Sinicum",
    "DuCange",
}

_lsj_short: dict[str, str] | None = None
_lsj_full: dict[str, dict] | None = None
_source_data: dict[str, dict[str, str]] | None = None
_accent_index: dict[str, set[str]] | None = None
_canonical_to_forms: dict[str, set[str]] | None = None
_display_forms: dict[str, str] | None = None
_english_index: dict[str, set[str]] | None = None
_translit_index: dict[str, set[str]] | None = None

SOURCE_ALIASES = {
    "middleliddell": "middle-liddell",
}


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text.strip().rstrip(".,;:!?·"))


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", stripped)


def _contains_greek(text: str) -> bool:
    return bool(re.search(r"[\u0370-\u03FF\u1F00-\u1FFF]", text))


def _canonical_form(word: str) -> str:
    return re.sub(r"\d+$", "", word)


def _tokenize_english(text: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z'-]{1,}", text.lower()))


def _ascii_fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", stripped)


def _normalize_translit_key(text: str) -> str:
    lowered = _ascii_fold(text).lower()
    return re.sub(r"[^a-z0-9]+", "", lowered)


def _short_preview_from_html(html_text: str, max_chars: int = 260) -> str:
    text = _strip_html(html_text)
    text = re.sub(r"\s+", " ", text).strip(" ,;:\n\t")
    text = re.sub(r"(?:\s*[;:,]\s*)?@+\s*$", "", text).strip()
    if len(text) > max_chars:
        return text[: max_chars - 3].rstrip() + "..."
    return text or "[no gloss]"


def _clean_short_def_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip(" ,;:\n\t")
    cleaned = re.sub(r"(?:\s*[;:,]\s*)?@+\s*$", "", cleaned).strip()
    return cleaned


def _is_latin_live_dico(dname: str) -> bool:
    if dname in LATIN_LIVE_DICO_NAMES:
        return True
    low = dname.lower()
    return any(
        token in low
        for token in (
            "latin",
            "lewis",
            "gaffiot",
            "ducange",
            "dmlbs",
            "georges",
            "latino",
        )
    )


async def _fetch_live_detail_payload(query: str) -> dict | None:
    cache_key = f"{LOGEION_CACHE_PREFIX}{query}"
    try:
        cached = await get_cache(cache_key)
    except Exception:
        cached = None

    if cached:
        try:
            parsed = json.loads(cached)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    try:
        async with httpx.AsyncClient(timeout=LOGEION_TIMEOUT_SECONDS, follow_redirects=True) as client:
            resp = await client.get(
                LOGEION_DETAIL_URL,
                params={"w": query, "type": "normal", "dicos": "all"},
                headers={"Accept": "application/json", "User-Agent": "ancientgreek/1.0"},
            )
    except Exception:
        return None

    if resp.status_code != 200:
        return None

    try:
        parsed = resp.json()
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None

    try:
        await set_cache(cache_key, json.dumps(parsed, ensure_ascii=False))
    except Exception:
        pass
    return parsed


async def _lookup_live_logeion(query: str) -> list[DictionaryEntry]:
    payload = await _fetch_live_detail_payload(query)
    if not payload:
        return []

    detail = payload.get("detail")
    if not isinstance(detail, dict):
        return []

    dicos = detail.get("dicos")
    if not isinstance(dicos, list) or not dicos:
        return []

    word = str(detail.get("headword") or query).strip() or query
    senses: list[DictionarySense] = []

    for dico in dicos:
        if not isinstance(dico, dict):
            continue
        dname = str(dico.get("dname") or "").strip()
        if not dname:
            continue
        if _is_latin_live_dico(dname):
            continue
        entries = dico.get("es")
        if isinstance(entries, str):
            entries = [entries]
        if not isinstance(entries, list):
            continue

        for html_entry in entries:
            if not isinstance(html_entry, str):
                continue
            html_entry = html_entry.strip()
            if not html_entry:
                continue
            senses.append(
                DictionarySense(
                    source=dname,
                    short_def=_short_preview_from_html(html_entry),
                    long_def=html_entry,
                )
            )

    if not senses:
        return []

    return [
        DictionaryEntry(
            word=_normalize(word),
            transliteration=transliterate(_normalize(word)),
            senses=senses,
            matched_by="headword" if _contains_greek(query) else "english",
            score=100.0,
        )
    ]


def _load_lsj_short() -> dict[str, str]:
    global _lsj_short
    if _lsj_short is None:
        raw = json.loads(LSJ_PATH.read_text(encoding="utf-8"))
        _lsj_short = {k: _clean_short_def_text(str(v)) for k, v in raw.items()}
    return _lsj_short


def _load_lsj_full() -> dict[str, dict]:
    global _lsj_full
    if _lsj_full is None:
        if not LSJ_FULL_PATH.exists() and LSJ_FULL_S3_URI:
            try:
                LSJ_FULL_PATH.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["aws", "s3", "cp", LSJ_FULL_S3_URI, str(LSJ_FULL_PATH)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except Exception:
                pass

        if LSJ_FULL_PATH.exists():
            _lsj_full = json.loads(LSJ_FULL_PATH.read_text(encoding="utf-8"))
        else:
            _lsj_full = {}
    return _lsj_full


def _load_dat(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        if "|" not in line:
            continue
        word, definition = line.split("|", 1)
        clean = unicodedata.normalize("NFC", word.lstrip("@").strip())
        if not clean:
            continue
        data[clean] = _clean_short_def_text(_strip_html(definition))
    return data


def _load_sources() -> dict[str, dict[str, str]]:
    global _source_data
    if _source_data is not None:
        return _source_data

    sources: dict[str, dict[str, str]] = {
        "lsj": _load_lsj_short(),
    }

    for dat_path in sorted(DICT_DIR.glob("*-short.dat")):
        source = dat_path.name.replace("-short.dat", "")
        source = SOURCE_ALIASES.get(source, source)
        if source == "lsj" or source in BLOCKED_LOCAL_SOURCES:
            continue
        data = _load_dat(dat_path)
        if source in sources:
            sources[source].update(data)
        else:
            sources[source] = data

    _source_data = sources
    return sources


def _build_indexes() -> None:
    global _accent_index, _canonical_to_forms, _display_forms, _english_index, _translit_index
    if (
        _accent_index is not None
        and _canonical_to_forms is not None
        and _display_forms is not None
        and _english_index is not None
        and _translit_index is not None
    ):
        return

    sources = _load_sources()
    accent_index: dict[str, set[str]] = defaultdict(set)
    canonical_to_forms: dict[str, set[str]] = defaultdict(set)
    display_forms: dict[str, str] = {}
    english_index: dict[str, set[str]] = defaultdict(set)
    translit_index: dict[str, set[str]] = defaultdict(set)

    for source, words in sources.items():
        for form, short_def in words.items():
            canonical = _canonical_form(form)
            canonical_to_forms[canonical].add(form)

            if canonical not in display_forms:
                display_forms[canonical] = canonical

            bare = _strip_accents(form).lower()
            accent_index[bare].add(canonical)

            for token in _tokenize_english(short_def):
                english_index[token].add(canonical)

            # Source name is indexable too (e.g. "Homeric" lexicon queries).
            english_index[source.lower()].add(canonical)

            translit_key = _normalize_translit_key(transliterate(form))
            if translit_key:
                translit_index[translit_key].add(canonical)

    _accent_index = accent_index
    _canonical_to_forms = canonical_to_forms
    _display_forms = display_forms
    _english_index = english_index
    _translit_index = translit_index


def warm_local_dictionary_cache() -> None:
    """Preload small local dictionaries and derived indexes into memory."""
    _load_sources()
    _build_indexes()


def _get_lsj_long_def(form: str) -> str | None:
    full = _load_lsj_full()
    entry = full.get(form) or full.get(form.lower())
    if not entry:
        return None
    html = str(entry.get("html", ""))
    if len(html) > MAX_LONG_DEF_CHARS:
        html = html[:MAX_LONG_DEF_CHARS] + '<p class="truncated">... [entry truncated]</p>'
    return html


def _entry_for(canonical: str, matched_by: str, score: float) -> DictionaryEntry | None:
    _build_indexes()
    assert _canonical_to_forms is not None
    forms = _canonical_to_forms.get(canonical)
    if not forms:
        return None

    senses: list[DictionarySense] = []
    seen_senses: set[tuple[str, str]] = set()
    sources = _load_sources()

    for source in SOURCE_PRIORITY:
        source_words = sources.get(source, {})
        for form in forms:
            short_def = source_words.get(form)
            if not short_def:
                continue
            dedupe_key = (source, short_def)
            if dedupe_key in seen_senses:
                continue
            seen_senses.add(dedupe_key)
            senses.append(
                DictionarySense(
                    source=source,
                    short_def=short_def,
                    long_def=None,
                )
            )

    # Include any non-priority sources at the end
    for source, source_words in sources.items():
        if source in SOURCE_PRIORITY:
            continue
        for form in forms:
            short_def = source_words.get(form)
            if not short_def:
                continue
            dedupe_key = (source, short_def)
            if dedupe_key in seen_senses:
                continue
            seen_senses.add(dedupe_key)
            senses.append(DictionarySense(source=source, short_def=short_def))

    if not senses:
        return None

    assert _display_forms is not None
    display_word = _display_forms.get(canonical, canonical)
    return DictionaryEntry(
        word=display_word,
        transliteration=transliterate(display_word),
        senses=senses,
        matched_by=matched_by,
        score=score,
    )


def _headword_candidates(query: str, max_candidates: int) -> list[tuple[str, float]]:
    _build_indexes()
    assert _accent_index is not None
    assert _canonical_to_forms is not None

    normalized = _normalize(query)
    lowered = normalized.lower()
    bare = _strip_accents(lowered)
    scores: dict[str, float] = {}
    sources = _load_sources()

    for source_words in sources.values():
        if normalized in source_words:
            canonical = _canonical_form(normalized)
            scores[canonical] = max(scores.get(canonical, 0), 100.0)
        if lowered in source_words:
            canonical = _canonical_form(lowered)
            scores[canonical] = max(scores.get(canonical, 0), 95.0)

    for canonical in _accent_index.get(bare, set()):
        scores[canonical] = max(scores.get(canonical, 0), 90.0)

    # Prefix fallback if no exact/near-exact hit.
    if not scores and len(lowered) >= 2:
        for canonical in _canonical_to_forms:
            candidate = canonical.lower()
            if not candidate.startswith(lowered):
                continue
            # Favor shorter distance to the query.
            distance = abs(len(candidate) - len(lowered))
            scores[canonical] = max(scores.get(canonical, 0), 70.0 - min(distance, 20))

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))
    return ranked[:max_candidates]


def _english_candidates(query: str, max_candidates: int) -> list[tuple[str, float]]:
    _build_indexes()
    assert _english_index is not None

    tokens = _tokenize_english(query)
    if not tokens:
        return []

    scores: dict[str, float] = defaultdict(float)
    for token in tokens:
        for canonical in _english_index.get(token, set()):
            scores[canonical] += 1.0

    phrase = query.lower().strip()
    if phrase:
        sources = _load_sources()
        for canonical in list(scores):
            forms = _canonical_to_forms.get(canonical, set()) if _canonical_to_forms else set()
            phrase_hits = 0
            for source_words in sources.values():
                for form in forms:
                    short_def = source_words.get(form, "")
                    if phrase in short_def.lower():
                        phrase_hits += 1
            if phrase_hits:
                scores[canonical] += 2.0 + phrase_hits * 0.5

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))
    return ranked[:max_candidates]


def _transliteration_candidates(query: str, max_candidates: int) -> list[tuple[str, float]]:
    _build_indexes()
    assert _translit_index is not None

    key = _normalize_translit_key(query)
    if len(key) < 2:
        return []

    scores: dict[str, float] = {}
    for canonical in _translit_index.get(key, set()):
        scores[canonical] = max(scores.get(canonical, 0.0), 96.0)

    if len(scores) < max_candidates:
        for indexed_key, canonicals in _translit_index.items():
            if indexed_key == key or not indexed_key.startswith(key):
                continue
            distance = abs(len(indexed_key) - len(key))
            score = 78.0 - min(distance, 20)
            for canonical in canonicals:
                scores[canonical] = max(scores.get(canonical, 0.0), score)

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))
    return ranked[:max_candidates]


async def lookup_word(word: str, max_results: int = 25) -> list[DictionaryEntry]:
    """Unified bilingual dictionary search (Greek headword or English gloss)."""
    query = _normalize(word)
    if not query:
        return []

    if _contains_greek(query):
        candidates = _headword_candidates(query, max_candidates=max_results * 3)
        matched_by_map = {canonical: "headword" for canonical, _ in candidates}
    else:
        english_candidates = _english_candidates(query, max_candidates=max_results * 3)
        translit_candidates = _transliteration_candidates(query, max_candidates=max_results * 3)

        merged_scores: dict[str, float] = {}
        matched_by_map: dict[str, str] = {}
        for canonical, score in english_candidates:
            prev = merged_scores.get(canonical, float("-inf"))
            if score > prev:
                merged_scores[canonical] = score
                matched_by_map[canonical] = "english"
        for canonical, score in translit_candidates:
            prev = merged_scores.get(canonical, float("-inf"))
            if score > prev:
                merged_scores[canonical] = score
                matched_by_map[canonical] = "transliteration"
            elif score == prev and matched_by_map.get(canonical) != "english":
                matched_by_map[canonical] = "transliteration"

        candidates = sorted(merged_scores.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))

    entries: list[DictionaryEntry] = []
    for canonical, score in candidates:
        entry = _entry_for(canonical, matched_by=matched_by_map.get(canonical, "headword"), score=score)
        if entry is not None:
            entries.append(entry)
        if len(entries) >= max_results:
            break

    return entries


async def lookup_word_live(word: str, max_results: int = 25) -> list[DictionaryEntry]:
    """Live Logeion detail lookup (all dictionaries, no filtering)."""
    query = _normalize(word)
    if not query:
        return []
    if not _contains_greek(query):
        return []

    entries = await _lookup_live_logeion(query)
    if entries:
        return entries[:max_results]

    # Fallback to local source data when live API is unavailable.
    return await lookup_word(query, max_results=max_results)
