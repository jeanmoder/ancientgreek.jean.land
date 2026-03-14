import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.anyio
async def test_catalog(client):
    resp = await client.get("/api/texts/catalog")
    assert resp.status_code == 200
    catalog = resp.json()
    assert len(catalog) >= 10
    for text in catalog:
        assert "id" in text
        assert "title" in text
        assert "author" in text
        assert "urn" in text


@pytest.mark.anyio
async def test_read_text(client):
    resp = await client.get("/api/texts/read/homer-iliad", params={"start": 1, "end": 5})
    assert resp.status_code == 200
    passage = resp.json()
    assert passage["text_id"] == "homer-iliad"
    assert len(passage["lines"]) > 0
    # Check lines have Greek text
    first_line = passage["lines"][0]["text"]
    assert any(0x0370 <= ord(c) <= 0x03FF or 0x1F00 <= ord(c) <= 0x1FFF for c in first_line)


@pytest.mark.anyio
async def test_read_nonexistent_text(client):
    resp = await client.get("/api/texts/read/does-not-exist")
    assert resp.status_code == 404
