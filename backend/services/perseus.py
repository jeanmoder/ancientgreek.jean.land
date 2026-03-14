import html
import json
import os
import re
from collections.abc import Iterable

import httpx

from backend.db import get_cache, set_cache
from backend.models.dictionary import MorphologyParse, MorphologyResult

MORPHEUS_URL = "https://morph.alpheios.net/api/v1/analysis"
PERSEUS_MORPH_URL = "http://www.perseus.tufts.edu/hopper/morph"
ODYCY_MODEL_CANDIDATES = ("grc_odycy_joint_trf", "grc_odycy_joint_sm")

GREEK_TOKEN_RE = re.compile(r"[\u0370-\u03FF\u1F00-\u1FFF]+")
ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
PCT_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*%")

_ODYCY_LOAD_ATTEMPTED = False
_ODYCY_NLP = None


def parse_signature(parse: MorphologyParse) -> str:
    detail_items = sorted(parse.details.items())
    detail_str = "|".join(f"{k}={v}" for k, v in detail_items)
    return f"{parse.lemma}|{parse.part_of_speech}|{detail_str}"


def extract_greek_tokens(text: str, max_tokens: int = 80) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []
    tokens = GREEK_TOKEN_RE.findall(normalized)
    if not tokens:
        return []
    return tokens[:max_tokens]


def _clean_word(word: str) -> str:
    return word.strip().strip(".,;:!?·")


def _strip_html(raw: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", raw)
    return html.unescape(without_tags).replace("\xa0", " ").strip()


def _normalize_analysis_token(token: str) -> str:
    t = token.lower().strip()
    mapping = {
        "singular": "sg",
        "plural": "pl",
        "dual": "dual",
        "masculine": "masc",
        "feminine": "fem",
        "neuter": "neut",
        "nominative": "nom",
        "genitive": "gen",
        "dative": "dat",
        "accusative": "acc",
        "vocative": "voc",
        "adjective": "adj",
        "adverb": "adv",
        "adposition": "prep",
        "preposition": "prep",
        "pronoun": "pron",
        "determiner": "article",
    }
    return mapping.get(t, t)


def _analysis_tokens(text: str) -> set[str]:
    parts = re.findall(r"[a-zA-Z]+", text.lower())
    return {_normalize_analysis_token(part) for part in parts}


def _analysis_to_pos_details(text: str) -> tuple[str, dict[str, str]]:
    tokens = [_normalize_analysis_token(t) for t in re.findall(r"[a-zA-Z0-9]+", text)]
    pos = "unknown"
    details: dict[str, str] = {}

    pos_map = {
        "adj": "adjective",
        "adjective": "adjective",
        "noun": "noun",
        "verb": "verb",
        "pron": "pronoun",
        "pronoun": "pronoun",
        "adv": "adverb",
        "adverb": "adverb",
        "prep": "preposition",
        "preposition": "preposition",
        "conj": "conjunction",
        "conjunction": "conjunction",
        "article": "article",
        "participle": "participle",
        "part": "participle",
        "particle": "particle",
        "numeral": "numeral",
    }

    cases = {"nom", "gen", "dat", "acc", "voc"}
    numbers = {"sg", "pl", "dual"}
    genders = {"masc", "fem", "neut"}
    tenses = {"pres", "imperf", "fut", "aor", "perf", "plupf"}
    moods = {"ind", "subj", "opt", "imperat", "inf", "part"}
    voices = {"act", "mid", "pass"}
    dialects = {"attic", "epic", "ionic", "aeolic", "doric"}

    dialect_hits: list[str] = []
    for token in tokens:
        if token in pos_map:
            pos = pos_map[token]
            continue
        if token in cases:
            details["case"] = token
            continue
        if token in numbers:
            details["num"] = token
            continue
        if token in genders:
            details["gend"] = token
            continue
        if token in tenses:
            details["tense"] = token
            continue
        if token in moods:
            details["mood"] = token
            continue
        if token in voices:
            details["voice"] = token
            continue
        if token in {"1st", "2nd", "3rd"}:
            details["pers"] = token[0]
            continue
        if token in dialects:
            dialect_hits.append(token)

    if dialect_hits:
        details["dial"] = " ".join(dialect_hits)

    return pos, details


def _parse_tokens_for_matching(parse: MorphologyParse) -> set[str]:
    tokens = _analysis_tokens(parse.part_of_speech)
    for value in parse.details.values():
        tokens.update(_analysis_tokens(value))
    # Frequent short forms from Morpheus/Perseus output:
    for value in parse.details.values():
        lower = value.lower()
        if lower in {"sg", "pl", "masc", "fem", "neut", "nom", "gen", "dat", "acc", "voc"}:
            tokens.add(lower)
    return tokens


def _get_odycy_model():
    global _ODYCY_LOAD_ATTEMPTED, _ODYCY_NLP
    if _ODYCY_LOAD_ATTEMPTED:
        return _ODYCY_NLP

    _ODYCY_LOAD_ATTEMPTED = True
    try:
        import spacy
    except Exception:
        _ODYCY_NLP = None
        return None

    preferred = os.getenv("ODYCY_MODEL", "").strip()
    candidates: Iterable[str] = (
        (preferred,) + ODYCY_MODEL_CANDIDATES if preferred else ODYCY_MODEL_CANDIDATES
    )

    for model_name in candidates:
        try:
            _ODYCY_NLP = spacy.load(model_name)
            return _ODYCY_NLP
        except Exception:
            continue

    _ODYCY_NLP = None
    return None


def _map_spacy_morph_to_details(morph_dict: dict[str, str]) -> dict[str, str]:
    key_map = {
        "Case": "case",
        "Number": "num",
        "Gender": "gend",
        "Tense": "tense",
        "Voice": "voice",
        "Mood": "mood",
        "Person": "pers",
        "Degree": "comp",
        "Dialect": "dial",
        "Decl": "decl",
        "Aspect": "aspect",
        "VerbForm": "verbform",
    }
    details: dict[str, str] = {}
    for key, value in morph_dict.items():
        mapped = key_map.get(key)
        if mapped and value:
            details[mapped] = value
    return details


def _parse_with_odycy(clean_word: str) -> list[MorphologyParse]:
    nlp = _get_odycy_model()
    if nlp is None:
        return []

    try:
        doc = nlp(clean_word)
    except Exception:
        return []

    parses: list[MorphologyParse] = []
    for token in doc:
        tok = token.text.strip()
        if not tok or not GREEK_TOKEN_RE.search(tok):
            continue
        details = _map_spacy_morph_to_details(token.morph.to_dict())
        parse = MorphologyParse(
            form=tok,
            lemma=token.lemma_.strip() or tok,
            part_of_speech=(token.pos_.strip().lower() or "unknown"),
            details=details,
        )
        parse.signature = parse_signature(parse)
        parses.append(parse)

    return parses


async def _parse_with_morpheus(clean_word: str) -> list[MorphologyParse]:
    parses: list[MorphologyParse] = []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{MORPHEUS_URL}/word",
                params={"word": clean_word, "lang": "grc", "engine": "morpheusgrc"},
                headers={"Accept": "application/json"},
                timeout=10.0,
            )

        if resp.status_code not in (200, 201):
            return []

        data = resp.json()
        body = data.get("RDF", {}).get("Annotation", {}).get("Body", [])
        if isinstance(body, dict):
            body = [body]
        for entry in body:
            rest = entry.get("rest", {}).get("entry", {})
            infl_list = rest.get("infl", [])
            if isinstance(infl_list, dict):
                infl_list = [infl_list]

            for infl in infl_list:
                details: dict[str, str] = {}
                for key in [
                    "case",
                    "num",
                    "gend",
                    "tense",
                    "voice",
                    "mood",
                    "pers",
                    "comp",
                    "dial",
                    "decl",
                ]:
                    val = infl.get(key, {})
                    if isinstance(val, dict) and "$" in val:
                        details[key] = val["$"]
                    elif isinstance(val, str):
                        details[key] = val

                hdwd = rest.get("dict", {}).get("hdwd", {})
                lemma = hdwd.get("$", clean_word) if isinstance(hdwd, dict) else str(hdwd)
                pofs = infl.get("pofs", {})
                pos = pofs.get("$", "unknown") if isinstance(pofs, dict) else str(pofs)
                parse = MorphologyParse(
                    form=clean_word,
                    lemma=lemma,
                    part_of_speech=pos,
                    details=details,
                )
                parse.signature = parse_signature(parse)
                parses.append(parse)
    except Exception:
        return []

    unique: list[MorphologyParse] = []
    seen: set[str] = set()
    for parse in parses:
        if parse.signature in seen:
            continue
        seen.add(parse.signature)
        unique.append(parse)
    return unique


async def _fetch_perseus_percentages(
    clean_word: str,
    prior: str | None = None,
    doc_ref: str | None = None,
    can: str | None = None,
    index: int | None = None,
) -> list[tuple[set[str], float, str]]:
    try:
        async with httpx.AsyncClient() as client:
            params: dict[str, str | int] = {"l": clean_word, "la": "greek"}
            if prior:
                params["prior"] = prior
            if doc_ref:
                params["d"] = doc_ref
            if can:
                params["can"] = can
            if index is not None:
                params["i"] = index
            resp = await client.get(
                PERSEUS_MORPH_URL,
                params=params,
                headers={"User-Agent": "Mozilla/5.0"},
                follow_redirects=True,
                timeout=10.0,
            )
        if resp.status_code != 200:
            return []
        html_body = resp.text
    except Exception:
        return []

    rows: list[tuple[set[str], float, str]] = []
    for row_html in ROW_RE.findall(html_body):
        cells = CELL_RE.findall(row_html)
        if len(cells) < 2:
            continue

        analysis_text = _strip_html(cells[1])
        pct: float | None = None
        for cell in reversed(cells):
            m = PCT_RE.search(_strip_html(cell))
            if m:
                pct = float(m.group(1))
                break
        if pct is None:
            continue

        tokens = _analysis_tokens(analysis_text)
        if tokens:
            rows.append((tokens, pct, analysis_text))

    return rows


async def _attach_perseus_percentages(
    clean_word: str,
    parses: list[MorphologyParse],
    prior: str | None = None,
    doc_ref: str | None = None,
    can: str | None = None,
    index: int | None = None,
) -> list[MorphologyParse]:
    if not parses:
        return parses

    percent_rows = await _fetch_perseus_percentages(
        clean_word,
        prior=prior,
        doc_ref=doc_ref,
        can=can,
        index=index,
    )
    if not percent_rows:
        return parses

    percent_rows.sort(key=lambda row: row[1], reverse=True)

    # If only one parse survives, expose a second alternative when top two
    # Perseus votes are within 20 percentage points.
    if len(parses) == 1:
        _, top_pct, top_label = percent_rows[0]
        parses[0].parse_pct = top_pct
        top_pos, top_details = _analysis_to_pos_details(top_label)
        if top_pos != "unknown":
            parses[0].part_of_speech = top_pos
        if top_details:
            parses[0].details = top_details
        parses[0].analysis_label = top_label
        parses[0].signature = parses[0].signature or parse_signature(parses[0])

        if len(percent_rows) > 1:
            _, second_pct, second_label = percent_rows[1]
            if (top_pct - second_pct) < 20.0:
                alt = parses[0].model_copy(deep=True)
                alt.parse_pct = second_pct
                second_pos, second_details = _analysis_to_pos_details(second_label)
                if second_pos != "unknown":
                    alt.part_of_speech = second_pos
                if second_details:
                    alt.details = second_details
                alt.analysis_label = second_label
                alt.signature = parse_signature(alt)
                if alt.signature != parses[0].signature:
                    return [parses[0], alt]
                # If morphological signature is identical, still keep both by
                # forcing a distinct signature for UI visibility.
                alt.signature = f"{alt.signature}|alt"
                return [parses[0], alt]

        return [parses[0]]

    scored: list[tuple[float, int, MorphologyParse]] = []
    for idx, parse in enumerate(parses):
        parse_tokens = _parse_tokens_for_matching(parse)
        best_pct: float | None = None
        best_overlap = -1.0
        best_label = ""

        for row_tokens, pct, label in percent_rows:
            overlap = len(parse_tokens & row_tokens)
            if overlap <= 0:
                continue
            ratio = overlap / max(1, len(parse_tokens))
            if ratio > best_overlap or (ratio == best_overlap and (best_pct or -1.0) < pct):
                best_overlap = ratio
                best_pct = pct
                best_label = label

        parse.parse_pct = best_pct
        if best_label:
            parse.analysis_label = best_label
        parse.signature = parse.signature or parse_signature(parse)
        sort_pct = best_pct if best_pct is not None else -1.0
        scored.append((sort_pct, idx, parse))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored]


async def parse_word(
    word: str,
    prior: str | None = None,
    doc_ref: str | None = None,
    can: str | None = None,
    index: int | None = None,
) -> MorphologyResult:
    """Parse a Greek word with Morpheus and rank by Perseus vote percentages."""
    clean_word = _clean_word(word)
    if not clean_word:
        return MorphologyResult(word=clean_word, parses=[])

    context_suffix = (
        f"{prior or ''}|{doc_ref or ''}|{can or ''}|"
        f"{index if index is not None else ''}"
    )
    cache_key = f"morph-v2:{clean_word}:{context_suffix}"
    cached = await get_cache(cache_key)
    if cached:
        data = json.loads(cached)
        return MorphologyResult(**data)

    parses = await _parse_with_morpheus(clean_word)

    for parse in parses:
        parse.signature = parse.signature or parse_signature(parse)

    parses = await _attach_perseus_percentages(
        clean_word,
        parses,
        prior=prior,
        doc_ref=doc_ref,
        can=can,
        index=index,
    )
    result = MorphologyResult(word=clean_word, parses=parses)
    await set_cache(cache_key, result.model_dump_json())
    return result
