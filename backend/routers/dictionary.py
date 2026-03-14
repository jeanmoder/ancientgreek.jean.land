import asyncio
import hashlib
import json
import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend.db import get_cache, set_cache
from backend.models.dictionary import DictionaryEntry, MorphologyParse, MorphologyResult
from backend.services import logeion, perseus
from backend.services.citation import build_citation
from backend.services.paradigms import get_rule_based_paradigms, get_wiktionary_paradigms
from backend.services.translate import translate_passage
from backend.services.transliterate import transliterate

router = APIRouter(prefix="/dictionary", tags=["dictionary"])
GREEK_RE = r"[\u0370-\u03FF\u1F00-\u1FFF]"


class FullLookupResult(BaseModel):
    word: str
    transliteration: str
    parses: list[MorphologyParse]
    preferred_parse: MorphologyParse | None = None
    definitions: list[DictionaryEntry]
    paradigms: list[dict[str, Any]] = []
    paradigm: dict[str, Any] | None = None
    citation_form: str = ""  # e.g. "λόγος, -ου, ὁ" or "λύω, λύσω, ..."


@router.get("/parse", response_model=MorphologyResult)
async def parse_word(
    word: str,
    prior: str | None = None,
    d: str | None = None,
    can: str | None = None,
    i: int | None = None,
) -> MorphologyResult:
    """Parse the morphology of a Greek word."""
    return await perseus.parse_word(word, prior=prior, doc_ref=d, can=can, index=i)


@router.get("/lookup", response_model=list[DictionaryEntry])
async def lookup_word(word: str) -> list[DictionaryEntry]:
    """Look up a Greek word in dictionaries."""
    return await logeion.lookup_word(word)


@router.get("/full", response_model=FullLookupResult)
async def full_lookup(
    word: str,
    live: bool = False,
    prior: str | None = None,
    d: str | None = None,
    can: str | None = None,
    i: int | None = None,
) -> FullLookupResult:
    """Combined morphology parse + dictionary lookup in one call.

    For inflected forms, resolves to the lemma for definitions.
    """
    cache_fingerprint = json.dumps(
        {"word": word, "live": live, "prior": prior, "d": d, "can": can, "i": i},
        ensure_ascii=False,
        sort_keys=True,
    )
    cache_key = (
        "dictionary:full:v2:"
        + hashlib.sha256(cache_fingerprint.encode("utf-8")).hexdigest()
    )
    cached = await get_cache(cache_key)
    if cached:
        try:
            return FullLookupResult.model_validate_json(cached)
        except Exception:
            pass

    morph = await perseus.parse_word(word, prior=prior, doc_ref=d, can=can, index=i)

    # Add transliteration to each parse
    for p in morph.parses:
        p.transliteration = transliterate(p.lemma)

    # Collect unique lemmas from morphology.
    lemmas: list[str] = []
    seen_lemmas: set[str] = set()
    for p in morph.parses:
        if p.lemma not in seen_lemmas:
            seen_lemmas.add(p.lemma)
            lemmas.append(p.lemma)

    # Look up definitions: prefer lemma(s), fall back to the raw word.
    lookup_fn = logeion.lookup_word_live if live else logeion.lookup_word
    defs: list[DictionaryEntry] = []
    for lemma in lemmas:
        defs.extend(await lookup_fn(lemma))

    # If morphology found no lemmas, or lemma lookup returned nothing,
    # look up the raw word too.
    if not defs:
        defs.extend(await lookup_fn(word))

    # Deduplicate definitions by headword (service already aggregates senses).
    seen: set[str] = set()
    unique_defs: list[DictionaryEntry] = []
    for d in defs:
        key = d.word
        if key not in seen:
            seen.add(key)
            unique_defs.append(d)

    preferred_parse = morph.parses[0] if morph.parses else None

    # Build paradigm tables from Wiktionary for all candidate lemmas.
    paradigms: list[dict[str, object]] = []
    for lemma in lemmas:
        tables = await get_wiktionary_paradigms(lemma)
        for table in tables:
            paradigms.append(table)

    if not paradigms and re.search(GREEK_RE, word):
        paradigms = await get_wiktionary_paradigms(word)

    # Fallback: grammatical-rule paradigms if Wiktionary has no table.
    if not paradigms and preferred_parse:
        paradigms = get_rule_based_paradigms(
            preferred_parse.lemma,
            preferred_parse.part_of_speech,
            preferred_parse.details,
        )

    paradigm = paradigms[0] if paradigms else None

    # Build citation form from preferred parse.
    citation_form = ""
    if preferred_parse:
        citation_form = build_citation(
            preferred_parse.lemma,
            preferred_parse.part_of_speech,
            declension=preferred_parse.details.get("decl", ""),
            gender=preferred_parse.details.get("gend", ""),
        )

    result = FullLookupResult(
        word=word,
        transliteration=transliterate(word),
        parses=morph.parses,
        preferred_parse=preferred_parse,
        definitions=unique_defs,
        paradigms=paradigms,
        paradigm=paradigm,
        citation_form=citation_form,
    )
    await set_cache(cache_key, result.model_dump_json())
    return result


class ParsedToken(BaseModel):
    token: str
    transliteration: str = ""
    glosses: list[str] = []
    gloss_items: list[dict[str, str]] = []
    top_parse: MorphologyParse | None = None
    parses: list[MorphologyParse] = []


class ParseTextResult(BaseModel):
    text: str
    tokens: list[ParsedToken]


class ParseTextRequest(BaseModel):
    text: str
    prior: str | None = None
    d: str | None = None
    can: str | None = None
    i: int | None = None


@router.post("/parse-text", response_model=ParseTextResult)
async def parse_text(req: ParseTextRequest) -> ParseTextResult:
    """Parse each Greek token in selected text for immediate popup display."""
    text = req.text
    cache_fingerprint = json.dumps(
        {"text": text, "prior": req.prior, "d": req.d, "can": req.can, "i": req.i},
        ensure_ascii=False,
        sort_keys=True,
    )
    cache_key = (
        "dictionary:parse-text:v2:"
        + hashlib.sha256(cache_fingerprint.encode("utf-8")).hexdigest()
    )
    cached = await get_cache(cache_key)
    if cached:
        try:
            return ParseTextResult.model_validate_json(cached)
        except Exception:
            pass

    tokens = perseus.extract_greek_tokens(text, max_tokens=80)
    if not tokens:
        return ParseTextResult(text=text, tokens=[])

    parse_sem = asyncio.Semaphore(8)

    async def parse_one(idx: int, token: str):
        async with parse_sem:
            return await perseus.parse_word(
                token,
                prior=tokens[idx - 1] if idx > 0 else req.prior,
                doc_ref=req.d,
                can=req.can,
                index=(req.i + idx) if req.i is not None else None,
            )

    morph_results = await asyncio.gather(*(parse_one(idx, token) for idx, token in enumerate(tokens)))
    lookup_lemmas: list[str] = []
    for token, morph in zip(tokens, morph_results, strict=False):
        if morph.parses:
            lookup_lemmas.append(morph.parses[0].lemma)
        else:
            lookup_lemmas.append(token)

    lookup_sem = asyncio.Semaphore(8)

    async def lookup_one(lemma: str):
        async with lookup_sem:
            return await logeion.lookup_word(lemma, max_results=5)

    dict_results = await asyncio.gather(*(lookup_one(lemma) for lemma in lookup_lemmas))

    def _source_rank(source: str) -> int:
        low = source.lower()
        if "lsj" in low:
            return 0
        if "middle-liddell" in low or "middleliddell" in low:
            return 1
        if "autenrieth" in low:
            return 2
        if "slater" in low:
            return 3
        return 10

    def _source_abbrev(source: str) -> str:
        low = source.lower()
        if "lsj" in low:
            return "LSJ"
        if "middle-liddell" in low or "middleliddell" in low:
            return "ML"
        if "autenrieth" in low:
            return "AUT"
        if "slater" in low:
            return "SL"
        letters = "".join(ch for ch in source if ch.isalnum())
        return (letters[:3] if letters else source[:3]).upper()

    def _extract_glosses(
        entries: list[DictionaryEntry], max_glosses: int = 3
    ) -> tuple[list[str], list[dict[str, str]]]:
        candidates: list[tuple[int, int, str, str]] = []
        seen: set[tuple[str, str]] = set()
        idx = 0

        for entry in entries:
            for sense in entry.senses:
                gloss = sense.short_def.strip()
                if not gloss:
                    continue
                abbrev = _source_abbrev(sense.source)
                key = (gloss, abbrev)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append((_source_rank(sense.source), idx, gloss, abbrev))
                idx += 1

        ranked = sorted(candidates, key=lambda x: (x[0], x[1]))[:max_glosses]
        gloss_items = [{"text": gloss, "source": abbrev} for _, _, gloss, abbrev in ranked]
        glosses = [item["text"] for item in gloss_items]
        return glosses, gloss_items

    parsed_tokens: list[ParsedToken] = []
    for token, morph, dict_entries, lemma in zip(
        tokens, morph_results, dict_results, lookup_lemmas, strict=False
    ):
        glosses, gloss_items = _extract_glosses(dict_entries)
        for parse in morph.parses:
            parse.transliteration = transliterate(parse.lemma)
        parsed_tokens.append(
            ParsedToken(
                token=token,
                transliteration=transliterate(lemma),
                glosses=glosses,
                gloss_items=gloss_items,
                top_parse=morph.parses[0] if morph.parses else None,
                parses=morph.parses,
            )
        )
    result = ParseTextResult(text=text, tokens=parsed_tokens)
    await set_cache(cache_key, result.model_dump_json())
    return result


class TranslateRequest(BaseModel):
    text: str


class TranslateResponse(BaseModel):
    text: str
    translation: str


@router.post("/translate", response_model=TranslateResponse)
async def translate_text(req: TranslateRequest) -> TranslateResponse:
    """Translate Ancient Greek text to English."""
    translation = await translate_passage(req.text)
    return TranslateResponse(text=req.text, translation=translation)
