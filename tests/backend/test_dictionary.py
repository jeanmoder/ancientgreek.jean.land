import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.services import logeion, paradigms


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.anyio
async def test_parse_endpoint_exists(client):
    word = "\u03bb\u03cc\u03b3\u03bf\u03c2"
    resp = await client.get("/api/dictionary/parse", params={"word": word})
    # Should return 200 even if external API is down (returns empty parses)
    assert resp.status_code == 200
    data = resp.json()
    assert "word" in data
    assert "parses" in data
    assert data["word"] == word


@pytest.mark.anyio
async def test_lookup_endpoint_exists(client):
    resp = await client.get(
        "/api/dictionary/lookup", params={"word": "\u03bb\u03cc\u03b3\u03bf\u03c2"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.anyio
async def test_full_endpoint_exists_and_shape(client):
    resp = await client.get(
        "/api/dictionary/full",
        params={"word": "\u03bb\u03cc\u03b3\u03bf\u03c2", "prior": "\u1f41"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "word" in data
    assert "parses" in data
    assert "definitions" in data
    assert "paradigms" in data
    assert "citation_form" in data


@pytest.mark.anyio
async def test_parse_text_endpoint_exists(client):
    resp = await client.post(
        "/api/dictionary/parse-text",
        json={"text": "\u03bb\u03cc\u03b3\u03bf\u03c2 \u03b5\u03c1\u03b3\u03bf\u03bd"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "text" in data
    assert "tokens" in data


@pytest.mark.anyio
async def test_lookup_supports_transliteration_queries(monkeypatch):
    monkeypatch.setattr(
        logeion,
        "_source_data",
        {
            "lsj": {
                "\u03c7\u03c1\u03cc\u03bd\u03bf\u03c2": "time",
                "\u03bb\u03cc\u03b3\u03bf\u03c2": "word",
            }
        },
    )
    monkeypatch.setattr(logeion, "_accent_index", None)
    monkeypatch.setattr(logeion, "_canonical_to_forms", None)
    monkeypatch.setattr(logeion, "_display_forms", None)
    monkeypatch.setattr(logeion, "_english_index", None)
    monkeypatch.setattr(logeion, "_translit_index", None)

    entries = await logeion.lookup_word("chronos")
    assert entries
    assert entries[0].word == "\u03c7\u03c1\u03cc\u03bd\u03bf\u03c2"
    assert entries[0].transliteration
    assert entries[0].matched_by == "transliteration"


def test_paradigm_titles_are_not_left_as_generic_inflection():
    tables = [
        {
            "title": "Inflection",
            "headers": ["Person", "Singular", "Plural"],
            "rows": [["1st", "\u03bb\u03cd\u03c9", "\u03bb\u03cd\u03bf\u03bc\u03b5\u03bd"]],
        },
        {
            "title": "",
            "headers": ["Case", "Singular", "Plural"],
            "rows": [["Nominative", "\u03bb\u03cc\u03b3\u03bf\u03c2", "\u03bb\u03cc\u03b3\u03bf\u03b9"]],
        },
    ]

    titled = paradigms._finalize_table_titles(tables, "\u03bb\u03cd\u03c9")

    assert titled[0]["title"].startswith("Verb Conjugation:")
    assert titled[1]["title"].startswith("Declension:")
