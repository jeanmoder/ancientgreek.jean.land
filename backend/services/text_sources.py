"""Text source: fetches TEI XML from GitHub (PerseusDL), caches locally, parses on-the-fly.

No JSON pre-processing — XML is the source of truth.
"""

import json
import unicodedata
from pathlib import Path

import httpx
from lxml import etree

from backend.db import get_cache, set_cache
from backend.models.texts import BookInfo, TextLine, TextPassage

XML_DIR = Path(__file__).parent.parent / "data" / "texts" / "xml"
CATALOG_PATH = Path(__file__).parent.parent / "data" / "texts" / "catalog.json"

NS = {"t": "http://www.tei-c.org/ns/1.0"}

# In-memory cache of parsed book structures: text_id -> list[dict]
_books_cache: dict[str, list[dict]] = {}
_xml_alias_cache: dict[str, Path | None] = {}


def _get_text(elem: etree._Element) -> str:
    """Extract all text from an element, NFC-normalized."""
    raw = etree.tostring(elem, method="text", encoding="unicode")
    text = " ".join(raw.split())
    return unicodedata.normalize("NFC", text.strip())


def _catalog_entry(text_id: str) -> dict | None:
    """Look up a text in the catalog."""
    if not CATALOG_PATH.exists():
        return None
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return next((t for t in catalog if t["id"] == text_id), None)


def _find_local_xml_alias(text_id: str, entry: dict) -> Path | None:
    """Find a local XML file matching catalog metadata when <text_id>.xml is absent."""
    if text_id in _xml_alias_cache:
        return _xml_alias_cache[text_id]

    expected_filename = Path(entry.get("github_path", "")).name.strip()
    expected_urn = str(entry.get("urn", "")).strip()

    for candidate in XML_DIR.glob("*.xml"):
        if not candidate.is_file():
            continue
        if candidate.name == f"{text_id}.xml":
            continue
        try:
            # Metadata is near the top of TEI headers; read only a small prefix.
            with candidate.open("rb") as fh:
                header = fh.read(256_000).decode("utf-8", errors="ignore")
        except Exception:
            continue

        if expected_filename and expected_filename in header:
            _xml_alias_cache[text_id] = candidate
            return candidate
        if expected_urn and expected_urn in header:
            _xml_alias_cache[text_id] = candidate
            return candidate

    _xml_alias_cache[text_id] = None
    return None


def _ensure_xml(text_id: str) -> Path | None:
    """Ensure the XML file is available locally, downloading from GitHub if needed."""
    # Check for existing local file (legacy or cached)
    local = XML_DIR / f"{text_id}.xml"
    if local.exists():
        return local

    # Look up github_path in catalog
    entry = _catalog_entry(text_id)
    if entry is None or not entry.get("github_path"):
        return None

    # Some locally mirrored files use older slug names. Resolve by TEI metadata
    # (idno / urn in header) before trying network fetch.
    alias = _find_local_xml_alias(text_id, entry)
    if alias is not None:
        return alias

    github_path = entry["github_path"]
    source_repo = entry.get("source_repo", "PerseusDL/canonical-greekLit")
    source_branch = entry.get("source_branch", "master")
    url = f"https://raw.githubusercontent.com/{source_repo}/{source_branch}/{github_path}"

    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        if resp.status_code == 200:
            XML_DIR.mkdir(parents=True, exist_ok=True)
            local.write_bytes(resp.content)
            return local
    except Exception:
        pass

    return None


def _parse_books(tree: etree._ElementTree) -> list[dict]:
    """Auto-detect text structure and parse into books with lines.

    Handles: poetry with <l> tags, prose with <p> tags,
    nested textpart divs (book > chapter > section), drama, etc.
    """
    body = tree.find(".//t:body", NS)
    if body is None:
        return []

    edition = body.find("t:div[@type='edition']", NS)
    if edition is None:
        # Some texts don't have an edition div; use body directly
        edition = body

    # Check structure: does edition have direct textpart children?
    top_parts = edition.findall("t:div[@type='textpart']", NS)

    if not top_parts:
        # No textpart divs — extract all text as a single "book"
        return _parse_flat(edition)

    # Check if top-level parts have sub-parts (book > chapter/section).
    # Prose texts can contain embedded <l> quotations; treat as poetry only when
    # the structure is line-based and lacks paragraphs.
    first_sub = top_parts[0].findall("t:div[@type='textpart']", NS)
    first_p_count = len(top_parts[0].findall(".//t:p", NS))
    first_l_count = len(top_parts[0].findall(".//t:l", NS))
    is_line_based = first_l_count > 0 and first_p_count == 0

    if is_line_based:
        return _parse_poetry(top_parts)
    if first_sub:
        return _parse_nested_prose(top_parts)
    return _parse_simple_prose(top_parts)


def _parse_poetry(parts: list[etree._Element]) -> list[dict]:
    """Parse poetry: textpart divs containing <l> line elements."""
    books = []
    for part in parts:
        n = part.get("n", "")
        subtype = part.get("subtype", "")
        label_prefix = subtype.capitalize() if subtype else "Book"
        lines = []
        for l_elem in part.findall(".//t:l", NS):
            ln = l_elem.get("n", "")
            text = _get_text(l_elem)
            if text:
                lines.append({"n": ln, "text": text})
        if lines:
            books.append({"n": n, "label": f"{label_prefix} {n}", "lines": lines})
    return books


def _parse_nested_prose(parts: list[etree._Element]) -> list[dict]:
    """Parse prose with nested textparts: book > chapter > section."""
    books = []
    for part in parts:
        n = part.get("n", "")
        subtype = part.get("subtype", "")
        label_prefix = subtype.capitalize() if subtype else "Book"
        lines: list[dict] = []
        _extract_nested_lines(part, [], lines)
        if lines:
            books.append({"n": n, "label": f"{label_prefix} {n}", "lines": lines})
    return books


def _extract_nested_lines(
    elem: etree._Element, ref_parts: list[str], lines: list[dict]
) -> None:
    """Recursively extract lines from nested textpart divs."""
    sub_parts = elem.findall("t:div[@type='textpart']", NS)
    if sub_parts:
        for sub in sub_parts:
            sub_n = sub.get("n", "")
            _extract_nested_lines(sub, ref_parts + [sub_n], lines)
    else:
        # Leaf node: extract text from <p>, <l>, or direct text
        ref = ".".join(ref_parts) if ref_parts else elem.get("n", "")
        p_elems = elem.findall(".//t:p", NS)
        if p_elems:
            for p_elem in p_elems:
                ln = p_elem.get("n", ref)
                text = _get_text(p_elem)
                if text:
                    lines.append({"n": ln, "text": text})
            return

        l_elems = elem.findall(".//t:l", NS)
        if l_elems:
            for l_elem in l_elems:
                ln = l_elem.get("n", ref)
                text = _get_text(l_elem)
                if text:
                    lines.append({"n": ln, "text": text})
            return

        text = _get_text(elem)
        if text:
            lines.append({"n": ref, "text": text})


def _parse_simple_prose(parts: list[etree._Element]) -> list[dict]:
    """Parse prose with simple textparts (sections, no sub-levels)."""
    # Group into a single "book" or treat each part as a book
    # Heuristic: if there are many parts (>20), treat each as a section in one book
    if len(parts) > 20:
        lines = []
        for part in parts:
            n = part.get("n", "")
            p_elems = part.findall(".//t:p", NS)
            if p_elems:
                for p in p_elems:
                    text = _get_text(p)
                    if text:
                        lines.append({"n": n, "text": text})
            else:
                text = _get_text(part)
                if text:
                    lines.append({"n": n, "text": text})
        if lines:
            return [{"n": "1", "label": "Full Text", "lines": lines}]
        return []

    books = []
    for part in parts:
        n = part.get("n", "")
        subtype = part.get("subtype", "")
        label_prefix = subtype.capitalize() if subtype else "Section"
        lines: list[dict] = []
        _extract_nested_lines(part, [], lines)
        if not lines:
            # Try direct text extraction
            p_elems = part.findall(".//t:p", NS)
            for p in p_elems:
                text = _get_text(p)
                if text:
                    lines.append({"n": n, "text": text})
            if not lines:
                text = _get_text(part)
                if text:
                    lines.append({"n": n, "text": text})
        if lines:
            books.append({"n": n, "label": f"{label_prefix} {n}", "lines": lines})
    return books


def _parse_flat(edition: etree._Element) -> list[dict]:
    """Parse a flat text with no textpart structure."""
    lines: list[dict] = []

    # Try <l> elements first
    l_elems = edition.findall(".//t:l", NS)
    if l_elems:
        for l_elem in l_elems:
            n = l_elem.get("n", str(len(lines) + 1))
            text = _get_text(l_elem)
            if text:
                lines.append({"n": n, "text": text})
    else:
        # Try <p> elements
        p_elems = edition.findall(".//t:p", NS)
        for i, p in enumerate(p_elems, 1):
            text = _get_text(p)
            if text:
                lines.append({"n": str(i), "text": text})

    if not lines:
        text = _get_text(edition)
        if text:
            lines.append({"n": "1", "text": text})

    if lines:
        return [{"n": "1", "label": "Full Text", "lines": lines}]
    return []


def _load_books(text_id: str) -> list[dict] | None:
    """Load and parse books for a text, using cache."""
    if text_id in _books_cache:
        return _books_cache[text_id]

    xml_path = _ensure_xml(text_id)
    if xml_path is None:
        return None

    try:
        tree = etree.parse(str(xml_path))  # noqa: S320
        books = _parse_books(tree)
        if books:
            _books_cache[text_id] = books
            return books
    except Exception:
        return None

    return None


def get_books(text_id: str) -> list[BookInfo] | None:
    """Get book listing for a text."""
    books = _load_books(text_id)
    if books is None:
        return None
    return [
        BookInfo(
            n=book["n"],
            label=book["label"],
            line_count=len(book["lines"]),
        )
        for book in books
    ]


async def fetch_passage(
    text_id: str,
    title: str,
    tei_title: str | None,
    author: str,
    urn: str,
    book: int = 1,
    start: int = 1,
    end: int = 50,
) -> TextPassage:
    """Fetch a passage from a text, parsing XML on-the-fly."""
    cache_key = f"texts:passage:v3:{text_id}:{book}:{start}:{end}"
    cached = await get_cache(cache_key)
    if cached:
        try:
            return TextPassage.model_validate_json(cached)
        except Exception:
            pass

    books = _load_books(text_id)

    if books is not None and 1 <= book <= len(books):
        book_data = books[book - 1]
        all_lines = book_data["lines"]
        start_idx = max(0, start - 1)
        end_idx = min(end, len(all_lines))
        lines = [
            TextLine(n=line["n"], text=line["text"])
            for line in all_lines[start_idx:end_idx]
        ]
        book_label = book_data["label"]
        book_n = book_data["n"]
    else:
        lines = [TextLine(n="1", text="(Text not available — try refreshing)")]
        book_label = f"Book {book}"
        book_n = str(book)

    if not lines:
        lines = [TextLine(n="1", text="(No lines in this range)")]

    result = TextPassage(
        text_id=text_id,
        title=title,
        tei_title=tei_title,
        author=author,
        urn=urn,
        book_n=book_n,
        book_label=book_label,
        passage_ref=f"{start}-{end}",
        lines=lines,
    )
    await set_cache(cache_key, result.model_dump_json())
    return result
