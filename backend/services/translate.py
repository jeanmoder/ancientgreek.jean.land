import httpx

from backend.config import get_settings
from backend.db import get_cache, set_cache

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


async def translate_passage(text: str) -> str:
    """Translate Ancient Greek text to English using OpenRouter."""
    normalized = text.strip()
    if not normalized:
        return ""

    cache_key = f"translate-openrouter:v1:{normalized[:300]}"
    cached = await get_cache(cache_key)
    if cached:
        return cached

    settings = get_settings()
    if not settings.OPENROUTER_API_KEY:
        return "(Translation unavailable: OPENROUTER_API_KEY is missing)"

    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": settings.TRANSLATE_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert Ancient Greek translator. "
                    "Translate the given Ancient Greek text into clear, accurate English. "
                    "Return only the translation."
                ),
            },
            {
                "role": "user",
                "content": f"Translate this Ancient Greek:\n\n{normalized}",
            },
        ],
        "max_tokens": 1000,
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                OPENROUTER_URL,
                json=payload,
                headers=headers,
                timeout=15.0,
            )
        if resp.status_code == 200:
            data = resp.json()
            translation = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            if translation:
                await set_cache(cache_key, translation)
                return translation
        else:
            try:
                err = resp.json().get("error", {}).get("message", "")
            except Exception:
                err = resp.text[:200]
            if err:
                return f"(Translation unavailable: {err})"
            return f"(Translation unavailable: OpenRouter HTTP {resp.status_code})"
    except httpx.TimeoutException:
        return "(Translation unavailable: translation request timed out)"
    except Exception as exc:
        return f"(Translation unavailable: {exc.__class__.__name__})"

    return "(Translation unavailable)"
