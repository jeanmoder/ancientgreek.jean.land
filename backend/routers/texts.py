import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from lxml import etree

from backend.models.texts import BooksResponse, TextInfo, TextPassage
from backend.services.syntax import analyze_syntax
from backend.services.text_sources import fetch_passage, get_books

router = APIRouter(prefix="/texts", tags=["texts"])

CATALOG_PATH = Path(__file__).parent.parent / "data" / "texts" / "catalog.json"
XML_DIR = Path(__file__).parent.parent / "data" / "texts" / "xml"
NS = {"t": "http://www.tei-c.org/ns/1.0"}
_metadata_cache: dict[str, dict[str, str | None]] = {}
_catalog_cache: list[TextInfo] | None = None


def _load_catalog() -> list[dict]:
    if not CATALOG_PATH.exists():
        return []
    return json.loads(CATALOG_PATH.read_text())


def _infer_dialect(author: str, title: str) -> str | None:
    author_lower = author.lower()
    title_lower = title.lower()
    if "homer" in author_lower:
        return "Epic Ionic"
    if "herodotus" in author_lower:
        return "Ionic"
    if "plato" in author_lower or "xenophon" in author_lower:
        return "Attic"
    if "sophocles" in author_lower or "aeschylus" in author_lower:
        return "Attic (Tragic)"
    if "aristotle" in author_lower or "thucydides" in author_lower:
        return "Attic"
    if "new testament" in author_lower or "nt " in title_lower or "john" in title_lower:
        return "Koine"
    if "lucian" in author_lower:
        return "Atticizing Koine"
    if "apollonius rhodius" in author_lower or "callimachus" in author_lower:
        return "Hellenistic Literary Greek"
    return None


def _year_from_xml(text_id: str) -> str | None:
    xml_path = XML_DIR / f"{text_id}.xml"
    if not xml_path.exists():
        return None

    try:
        tree = etree.parse(str(xml_path))  # noqa: S320
    except Exception:
        return None

    candidates: list[str] = []
    xpaths = [
        ".//t:sourceDesc//t:imprint//t:date/text()",
        ".//t:sourceDesc//t:date/text()",
        ".//t:publicationStmt//t:date[not(@type='release')]/text()",
    ]
    for xpath in xpaths:
        nodes = tree.xpath(xpath, namespaces=NS)
        for node in nodes:
            text = str(node).strip()
            if text:
                candidates.append(text)

    for cand in candidates:
        match = re.search(r"([0-9]{3,4}(?:\s*-\s*[0-9]{2,4})?)", cand)
        if match:
            return match.group(1).replace(" ", "")
    return None


def _tei_title_from_xml(text_id: str) -> str | None:
    xml_path = XML_DIR / f"{text_id}.xml"
    if not xml_path.exists():
        return None

    try:
        tree = etree.parse(str(xml_path))  # noqa: S320
    except Exception:
        return None

    nodes = tree.xpath(".//t:titleStmt/t:title/text()", namespaces=NS)
    for node in nodes:
        text = str(node).strip()
        if text:
            return text
    return None


def _catalog_metadata(entry: dict) -> dict[str, str | None]:
    text_id = entry.get("id", "")
    if text_id in _metadata_cache:
        return _metadata_cache[text_id]

    metadata = {
        "tei_title": _tei_title_from_xml(text_id),
        "year": _year_from_xml(text_id),
        "dialect": _infer_dialect(str(entry.get("author", "")), str(entry.get("title", ""))),
    }
    _metadata_cache[text_id] = metadata
    return metadata


@router.get("/catalog", response_model=list[TextInfo])
async def get_catalog() -> list[TextInfo]:
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache

    enriched: list[TextInfo] = []
    for entry in _load_catalog():
        metadata = _catalog_metadata(entry)
        payload = {**entry}
        if not payload.get("tei_title"):
            payload["tei_title"] = metadata.get("tei_title")
        if not payload.get("year"):
            payload["year"] = metadata.get("year")
        if not payload.get("dialect"):
            payload["dialect"] = metadata.get("dialect")
        enriched.append(TextInfo(**payload))
    _catalog_cache = enriched
    return _catalog_cache


@router.get("/books/{text_id}", response_model=BooksResponse)
async def list_books(text_id: str) -> BooksResponse:
    text_info = next((t for t in _load_catalog() if t["id"] == text_id), None)
    if not text_info:
        raise HTTPException(status_code=404, detail="Text not found")

    books = get_books(text_id)
    if books is None:
        raise HTTPException(status_code=404, detail="Text data not found")

    return BooksResponse(books=books)


@router.get("/read/{text_id}", response_model=TextPassage)
async def read_text(
    text_id: str,
    book: int = 1,
    start: int = 1,
    end: int = 50,
) -> TextPassage:
    text_info = next((t for t in _load_catalog() if t["id"] == text_id), None)
    if not text_info:
        raise HTTPException(status_code=404, detail="Text not found")
    metadata = _catalog_metadata(text_info)
    tei_title = text_info.get("tei_title") or metadata.get("tei_title")

    return await fetch_passage(
        text_id=text_info["id"],
        title=text_info["title"],
        tei_title=tei_title,
        author=text_info["author"],
        urn=text_info["urn"],
        book=book,
        start=start,
        end=end,
    )


@router.post("/syntax")
async def get_syntax(request: dict) -> list[dict]:
    """Analyze syntax of a Greek line."""
    line = request.get("line", "")
    try:
        return await analyze_syntax(line)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
