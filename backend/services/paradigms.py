"""Wiktionary-backed Ancient Greek morphology tables for dictionary entries."""

from __future__ import annotations

import json
import re
import unicodedata
from urllib.parse import quote

import httpx
from lxml import html

from backend.db import get_cache, set_cache

ParadigmTable = dict[str, object]
WIKTIONARY_API_URL = "https://en.wiktionary.org/w/api.php"
WIKTIONARY_HEADERS = {
    "User-Agent": "AncientGreekTools/1.0 (+local development; contact unavailable)"
}

_TABLE_KEYWORDS = {
    "declension",
    "conjugation",
    "inflection",
    "paradigm",
    "noun forms",
    "verb forms",
    "adjective forms",
    "participle",
}
_MAX_TABLES = 16
_MAX_ROWS = 140
_MAX_COLS = 14
_LATIN_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_LATIN_LOWER = "abcdefghijklmnopqrstuvwxyz"
_GREEK_CHAR_RE = re.compile(r"[\u0370-\u03FF\u1F00-\u1FFF]")
_SAFE_CELL_CHARS_RE = re.compile(r"[^\u0370-\u03FF\u1F00-\u1FFF\s0-9·;.,;:!?()'’\-–—/\[\]]+")
_GENERIC_TITLE_KEYS = {
    "",
    "ancientgreek",
    "greek",
    "inflection",
    "inflections",
    "wiktionaryinflection",
    "declension",
    "conjugation",
    "forms",
}


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", stripped)


def _stem(lemma: str, ending: str) -> str:
    normalized_lemma = _normalize(lemma)
    bare_lemma = _strip_accents(normalized_lemma)
    bare_ending = _strip_accents(ending)
    if bare_lemma.endswith(bare_ending):
        return normalized_lemma[: -len(ending)]
    if normalized_lemma.endswith(ending):
        return normalized_lemma[: -len(ending)]
    return normalized_lemma


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text.strip())


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_text(node) -> str:
    # Strip footnote superscripts before collecting text.
    for sup in node.xpath(".//sup[contains(@class, 'reference')]"):
        parent = sup.getparent()
        if parent is not None:
            parent.remove(sup)
    # Strip transliteration spans (Latin-script helpers) so cells keep only
    # Greek inflected forms from Wiktionary tables.
    for tr_node in node.xpath(
        ".//*[contains(@lang, 'Latn') or "
        "contains(concat(' ', normalize-space(@class), ' '), ' Latn ') or "
        "contains(concat(' ', normalize-space(@class), ' '), ' mention-tr ') or "
        "(contains(concat(' ', normalize-space(@class), ' '), ' tr ') and "
        "contains(concat(' ', normalize-space(@class), ' '), ' transliteration '))]"
    ):
        parent = tr_node.getparent()
        if parent is not None:
            parent.remove(tr_node)
    return _clean_text("".join(node.itertext()))


def _clean_inflection_cell(text: str) -> str:
    """Drop inline Latin transliteration while keeping Greek forms in cells."""
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    if not _GREEK_CHAR_RE.search(cleaned):
        return cleaned
    # Cells with Greek often append Romanization without separators
    # (e.g., "λόγοςho lógos"). Keep Greek and neutral punctuation only.
    stripped = _SAFE_CELL_CHARS_RE.sub("", cleaned)
    return _clean_text(stripped)


def _title_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _is_generic_title(text: str) -> bool:
    if not text.strip():
        return True
    key = _title_key(text)
    if key in _GENERIC_TITLE_KEYS:
        return True
    return bool(re.fullmatch(r"inflectionof", key))


def _infer_table_kind(headers: list[str], rows: list[list[str]], hint: str = "") -> str:
    first_col = " ".join(row[0] for row in rows[:12] if row and row[0])
    signal = " ".join(headers + [first_col, hint]).lower()
    if "person" in signal or re.search(r"\b(?:1st|2nd|3rd)\b", signal):
        return "conjugation"
    if "participle" in signal:
        return "participle"
    if "case" in signal or any(token in signal for token in ("masc", "fem", "neut", "gender")):
        return "declension"
    if "comparative" in signal or "superlative" in signal:
        return "comparison"
    return "inflection"


def _finalize_table_titles(tables: list[ParadigmTable], lemma: str) -> list[ParadigmTable]:
    if not tables:
        return tables

    for table in tables:
        raw_title = _clean_text(str(table.get("title") or ""))
        headers = [str(cell) for cell in table.get("headers", []) if isinstance(cell, str)]
        rows = [row for row in table.get("rows", []) if isinstance(row, list)]

        if _is_generic_title(raw_title):
            kind = _infer_table_kind(headers, rows, raw_title)
            if kind == "conjugation":
                raw_title = f"Verb Conjugation: {lemma}"
            elif kind == "declension":
                raw_title = f"Declension: {lemma}"
            elif kind == "participle":
                raw_title = f"Participle Forms: {lemma}"
            elif kind == "comparison":
                raw_title = f"Adjective Comparison: {lemma}"
            else:
                raw_title = f"Inflection: {lemma}"
        table["title"] = raw_title

    counts: dict[str, int] = {}
    totals: dict[str, int] = {}
    for table in tables:
        title = str(table.get("title") or "").strip()
        totals[title] = totals.get(title, 0) + 1

    for table in tables:
        title = str(table.get("title") or "").strip()
        if totals.get(title, 0) <= 1:
            continue
        counts[title] = counts.get(title, 0) + 1
        table["title"] = f"{title} ({counts[title]})"

    return tables


def _parse_table(table, fallback_title: str, source_url: str) -> ParadigmTable | None:
    rows: list[list[str]] = []
    for tr in table.xpath(".//tr")[:_MAX_ROWS]:
        cells = tr.xpath("./th|./td")[:_MAX_COLS]
        if not cells:
            continue
        row = [_clean_inflection_cell(_extract_text(cell)) for cell in cells]
        while row and not row[-1]:
            row.pop()
        if row and any(cell for cell in row):
            rows.append(row)

    if len(rows) < 2:
        return None

    width = max(len(row) for row in rows)
    if width < 2:
        return None

    normalized_rows = [row + [""] * (width - len(row)) for row in rows]
    headers = normalized_rows[0]
    body = normalized_rows[1:]
    note: str | None = None
    filtered_body: list[list[str]] = []
    for row in body:
        first = row[0].strip() if row else ""
        if first and re.match(r"^notes?\s*:?\s*", first, flags=re.IGNORECASE):
            parts: list[str] = []
            lead = re.sub(r"^notes?\s*:?\s*", "", first, flags=re.IGNORECASE).strip()
            if lead:
                parts.append(lead)
            parts.extend(cell.strip() for cell in row[1:] if cell.strip())
            collapsed = _clean_text(" ".join(parts))
            if collapsed:
                note = collapsed
            continue
        filtered_body.append(row)
    body = filtered_body
    if not body:
        return None

    caption = _extract_text(table.xpath("./caption")[0]) if table.xpath("./caption") else ""
    if not caption:
        nav_heads = table.xpath(
            ".//*[contains(translate(@class, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'navhead')]"
        )
        for node in nav_heads[:2]:
            candidate = _extract_text(node)
            if candidate:
                caption = candidate
                break
    title = caption or fallback_title
    if not title:
        title = "Wiktionary Inflection"

    return {
        "title": title,
        "headers": headers,
        "rows": body,
        "note": note,
        "source": "wiktionary",
        "source_url": source_url,
    }


def _is_inflection_table(table, section_label: str) -> bool:
    classes = (table.get("class") or "").lower()
    caption = ""
    captions = table.xpath("./caption")
    if captions:
        caption = _extract_text(captions[0]).lower()
    ancestor_classes = " ".join(
        (ancestor.get("class") or "").lower() for ancestor in table.xpath("./ancestor::*")
    )
    descriptor = f"{classes} {ancestor_classes} {caption} {section_label.lower()}"

    if "inflection-table" in classes:
        return True
    if "navframe" in descriptor and "inflection" in descriptor:
        return True
    return any(keyword in descriptor for keyword in _TABLE_KEYWORDS)


def _extract_section_tables(
    doc,
    section_id_prefixes: tuple[str, ...],
    source_url: str,
    default_label: str,
) -> list[ParadigmTable]:
    prefix_expr = " or ".join(f"starts-with(@id, '{prefix}')" for prefix in section_id_prefixes)
    text_expr = (
        "contains(translate(normalize-space(string(.)), "
        f"'{_LATIN_UPPER}', '{_LATIN_LOWER}'), 'ancient greek') or "
        "contains(translate(normalize-space(string(.)), "
        f"'{_LATIN_UPPER}', '{_LATIN_LOWER}'), 'greek')"
    )
    h2_nodes = doc.xpath(
        f"//h2[{prefix_expr} or .//span[{prefix_expr}] or {text_expr}]"
    )
    if not h2_nodes:
        return []

    start_h2 = h2_nodes[0]
    start_parent = start_h2.getparent()
    start = start_parent if start_parent is not None else start_h2
    tables: list[ParadigmTable] = []
    seen_signatures: set[str] = set()
    current_section = default_label

    node = start.getnext()
    while node is not None:
        tag_obj = getattr(node, "tag", "")
        tag = tag_obj.lower() if isinstance(tag_obj, str) else ""
        classes = (node.get("class") or "").lower() if hasattr(node, "get") else ""

        # Stop at next language-level heading.
        if tag == "h2" or "mw-heading2" in classes or node.xpath("./h2"):
            break

        heading_nodes = node.xpath("./h3|./h4|./h5")
        if not heading_nodes and tag in {"h3", "h4", "h5"}:
            heading_nodes = [node]
        if heading_nodes:
            heading = _clean_text("".join(heading_nodes[0].itertext()))
            heading = re.sub(r"\[\s*edit\s*\]$", "", heading, flags=re.IGNORECASE).strip()
            if heading:
                current_section = heading

        for table in node.xpath("self::table | .//table"):
            if not _is_inflection_table(table, current_section):
                continue
            parsed = _parse_table(table, current_section or default_label, source_url)
            if parsed is None:
                continue
            signature = json.dumps(
                [parsed["title"], parsed["headers"], parsed["rows"][:3]], ensure_ascii=False
            )
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            tables.append(parsed)
            if len(tables) >= _MAX_TABLES:
                return tables
        node = node.getnext()

    return tables


async def _fetch_wiktionary_html(lemma: str) -> str | None:
    params = {
        "action": "parse",
        "page": lemma,
        "format": "json",
        "prop": "text",
        "redirects": "1",
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                WIKTIONARY_API_URL,
                params=params,
                headers=WIKTIONARY_HEADERS,
                timeout=12.0,
            )
        if resp.status_code != 200:
            return None
        payload = resp.json()
    except Exception:
        return None

    parse = payload.get("parse")
    if not isinstance(parse, dict):
        return None
    text_obj = parse.get("text")
    if not isinstance(text_obj, dict):
        return None
    html_text = text_obj.get("*")
    if not isinstance(html_text, str) or not html_text.strip():
        return None
    return html_text


async def get_wiktionary_paradigms(lemma: str) -> list[ParadigmTable]:
    """Return morphology tables for a lemma from Wiktionary's Ancient Greek section."""
    normalized = _normalize(lemma)
    if not normalized:
        return []

    cache_key = f"wiktionary-paradigms:v6:{normalized}"
    cached = await get_cache(cache_key)
    if cached:
        try:
            payload = json.loads(cached)
            if isinstance(payload, list):
                return payload
        except Exception:
            pass

    html_text = await _fetch_wiktionary_html(normalized)
    if not html_text:
        return []

    try:
        doc = html.fromstring(html_text)
    except Exception:
        await set_cache(cache_key, "[]")
        return []

    source_url = f"https://en.wiktionary.org/wiki/{quote(normalized)}#Ancient_Greek"
    tables = _extract_section_tables(
        doc,
        section_id_prefixes=("Ancient_Greek",),
        source_url=source_url,
        default_label="Ancient Greek",
    )
    if not tables:
        greek_source_url = f"https://en.wiktionary.org/wiki/{quote(normalized)}#Greek"
        tables = _extract_section_tables(
            doc,
            section_id_prefixes=("Greek",),
            source_url=greek_source_url,
            default_label="Greek",
        )
    tables = _finalize_table_titles(tables, normalized)

    await set_cache(cache_key, json.dumps(tables, ensure_ascii=False))
    return tables


def _rule_noun_paradigms(lemma: str, declension: str, gender: str) -> list[ParadigmTable]:
    decl = declension.strip().lower()
    gend = gender.strip().lower()
    bare = _strip_accents(lemma)
    tables: list[ParadigmTable] = []

    # Heuristic fallback when morphology metadata omits declension/gender.
    if not decl and not gend:
        if bare.endswith("ος"):
            decl = "2"
            gend = "masc"
        elif bare.endswith("ον"):
            decl = "2"
            gend = "neut"
        elif bare.endswith("η"):
            decl = "1"
            gend = "fem"
        elif bare.endswith("α"):
            decl = "1"
            gend = "fem"

    if ("2" in decl or "second" in decl) and ("masc" in gend):
        stem = _stem(lemma, "ος")
        tables.append(
            {
                "title": f"2nd Declension Masculine: {lemma}",
                "headers": ["Case", "Singular", "Dual", "Plural"],
                "rows": [
                    ["Nominative", f"{stem}ος", f"{stem}ω", f"{stem}οι"],
                    ["Genitive", f"{stem}ου", f"{stem}οιν", f"{stem}ων"],
                    ["Dative", f"{stem}ῳ", f"{stem}οιν", f"{stem}οις"],
                    ["Accusative", f"{stem}ον", f"{stem}ω", f"{stem}ους"],
                    ["Vocative", f"{stem}ε", f"{stem}ω", f"{stem}οι"],
                ],
            }
        )

    if ("2" in decl or "second" in decl) and ("neut" in gend):
        stem = _stem(lemma, "ον")
        tables.append(
            {
                "title": f"2nd Declension Neuter: {lemma}",
                "headers": ["Case", "Singular", "Dual", "Plural"],
                "rows": [
                    ["Nominative", f"{stem}ον", f"{stem}ω", f"{stem}α"],
                    ["Genitive", f"{stem}ου", f"{stem}οιν", f"{stem}ων"],
                    ["Dative", f"{stem}ῳ", f"{stem}οιν", f"{stem}οις"],
                    ["Accusative", f"{stem}ον", f"{stem}ω", f"{stem}α"],
                    ["Vocative", f"{stem}ον", f"{stem}ω", f"{stem}α"],
                ],
            }
        )

    if ("1" in decl or "first" in decl) and ("fem" in gend):
        if bare.endswith("η"):
            stem = _stem(lemma, "η")
            tables.append(
                {
                    "title": f"1st Declension Feminine (eta-stem): {lemma}",
                    "headers": ["Case", "Singular", "Dual", "Plural"],
                    "rows": [
                        ["Nominative", f"{stem}η", f"{stem}α", f"{stem}αι"],
                        ["Genitive", f"{stem}ης", f"{stem}αιν", f"{stem}ων"],
                        ["Dative", f"{stem}ῃ", f"{stem}αιν", f"{stem}αις"],
                        ["Accusative", f"{stem}ην", f"{stem}α", f"{stem}ας"],
                        ["Vocative", f"{stem}η", f"{stem}α", f"{stem}αι"],
                    ],
                }
            )
        elif bare.endswith("α"):
            stem = _stem(lemma, "α")
            tables.append(
                {
                    "title": f"1st Declension Feminine (alpha-stem): {lemma}",
                    "headers": ["Case", "Singular", "Dual", "Plural"],
                    "rows": [
                        ["Nominative", f"{stem}α", f"{stem}α", f"{stem}αι"],
                        ["Genitive", f"{stem}ας", f"{stem}αιν", f"{stem}ων"],
                        ["Dative", f"{stem}ᾳ", f"{stem}αιν", f"{stem}αις"],
                        ["Accusative", f"{stem}αν", f"{stem}α", f"{stem}ας"],
                        ["Vocative", f"{stem}α", f"{stem}α", f"{stem}αι"],
                    ],
                }
            )

    return tables


def _rule_adjective_paradigms(lemma: str, declension: str) -> list[ParadigmTable]:
    decl = declension.strip().lower()
    bare = _strip_accents(lemma)
    if not (("1" in decl or "2" in decl) and bare.endswith("ος")):
        return []

    stem = _stem(lemma, "ος")
    return [
        {
            "title": f"1st/2nd Declension Adjective: {lemma}",
            "headers": [
                "Case",
                "Masc. Sg.",
                "Fem. Sg.",
                "Neut. Sg.",
                "Masc. Pl.",
                "Fem. Pl.",
                "Neut. Pl.",
            ],
            "rows": [
                [
                    "Nom.",
                    f"{stem}ος",
                    f"{stem}η / {stem}α",
                    f"{stem}ον",
                    f"{stem}οι",
                    f"{stem}αι",
                    f"{stem}α",
                ],
                [
                    "Gen.",
                    f"{stem}ου",
                    f"{stem}ης / {stem}ας",
                    f"{stem}ου",
                    f"{stem}ων",
                    f"{stem}ων",
                    f"{stem}ων",
                ],
                [
                    "Dat.",
                    f"{stem}ῳ",
                    f"{stem}ῃ / {stem}ᾳ",
                    f"{stem}ῳ",
                    f"{stem}οις",
                    f"{stem}αις",
                    f"{stem}οις",
                ],
                [
                    "Acc.",
                    f"{stem}ον",
                    f"{stem}ην / {stem}αν",
                    f"{stem}ον",
                    f"{stem}ους",
                    f"{stem}ας",
                    f"{stem}α",
                ],
            ],
        }
    ]


def _rule_verb_paradigms(lemma: str) -> list[ParadigmTable]:
    bare = _strip_accents(lemma)
    if not bare.endswith("ω"):
        return []

    stem = _stem(lemma, "ω")
    fut_stem = f"{stem}σ"
    aor_stem = f"{stem}σ"
    return [
        {
            "title": f"Present Active Indicative: {lemma}",
            "headers": ["Person", "Singular", "Plural"],
            "rows": [
                ["1st", f"{stem}ω", f"{stem}ομεν"],
                ["2nd", f"{stem}εις", f"{stem}ετε"],
                ["3rd", f"{stem}ει", f"{stem}ουσι(ν)"],
            ],
        },
        {
            "title": f"Present Middle/Passive Indicative: {lemma}",
            "headers": ["Person", "Singular", "Plural"],
            "rows": [
                ["1st", f"{stem}ομαι", f"{stem}ομεθα"],
                ["2nd", f"{stem}ῃ/ει", f"{stem}εσθε"],
                ["3rd", f"{stem}εται", f"{stem}ονται"],
            ],
        },
        {
            "title": f"Future Active Indicative: {lemma}",
            "headers": ["Person", "Singular", "Plural"],
            "rows": [
                ["1st", f"{fut_stem}ω", f"{fut_stem}ομεν"],
                ["2nd", f"{fut_stem}εις", f"{fut_stem}ετε"],
                ["3rd", f"{fut_stem}ει", f"{fut_stem}ουσι(ν)"],
            ],
        },
        {
            "title": f"Aorist Active Indicative: {lemma}",
            "headers": ["Person", "Singular", "Plural"],
            "rows": [
                ["1st", f"ἐ{aor_stem}α", f"ἐ{aor_stem}αμεν"],
                ["2nd", f"ἐ{aor_stem}ας", f"ἐ{aor_stem}ατε"],
                ["3rd", f"ἐ{aor_stem}ε(ν)", f"ἐ{aor_stem}αν"],
            ],
        },
    ]


def get_rule_based_paradigms(
    lemma: str,
    part_of_speech: str,
    details: dict[str, str] | None = None,
) -> list[ParadigmTable]:
    """Fallback grammatical-rule paradigms when Wiktionary has no table."""
    details = details or {}
    pos = part_of_speech.lower().strip()
    result: list[ParadigmTable] = []

    if "noun" in pos:
        result = _rule_noun_paradigms(lemma, details.get("decl", ""), details.get("gend", ""))
    elif "adjective" in pos:
        result = _rule_adjective_paradigms(lemma, details.get("decl", ""))
    elif "verb" in pos:
        result = _rule_verb_paradigms(lemma)

    for table in result:
        table["source"] = "rule-based"
        table["source_url"] = None
    return result
