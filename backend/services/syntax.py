import json
import os
import re

from backend.db import get_cache, set_cache
DEFAULT_ODYCY_MODEL = "grc_odycy_joint_sm"
GREEK_TOKEN_RE = re.compile(r"[\u0370-\u03FF\u1F00-\u1FFF]+")
_LOAD_ATTEMPTED = False
_NLP = None
_LOAD_ERROR = ""


def _normalize_role(role: str) -> str:
    if role in {
        "subject",
        "verb",
        "object",
        "complement",
        "modifier",
        "particle",
        "conjunction",
        "preposition",
        "prepositional_complement",
        "apposition",
        "article",
    }:
        return role
    return "other"


def _get_odycy_model():
    global _LOAD_ATTEMPTED, _NLP, _LOAD_ERROR
    if _LOAD_ATTEMPTED:
        return _NLP

    _LOAD_ATTEMPTED = True
    try:
        import spacy
    except Exception as exc:
        _NLP = None
        _LOAD_ERROR = f"spaCy import failed: {exc}"
        return None

    model_name = os.getenv("ODYCY_MODEL", DEFAULT_ODYCY_MODEL).strip() or DEFAULT_ODYCY_MODEL
    try:
        _NLP = spacy.load(model_name)
        _LOAD_ERROR = ""
        return _NLP
    except Exception as exc:
        _NLP = None
        _LOAD_ERROR = f"Cannot load odyCy model '{model_name}': {exc}"
        return None


def ensure_odycy_model() -> None:
    """Fail fast when odyCy is unavailable so syntax never silently falls back."""
    nlp = _get_odycy_model()
    if nlp is None:
        raise RuntimeError(_LOAD_ERROR or "odyCy model is unavailable")


def _token_role(token) -> str:
    dep = token.dep_.lower()
    pos = token.pos_.upper()
    morph = token.morph.to_dict()

    if pos == "ADP":
        return "preposition"
    if pos == "DET":
        return "article"
    if pos in {"CCONJ", "SCONJ", "CONJ"}:
        return "conjunction"
    if pos in {"PART", "INTJ"}:
        return "particle"

    if dep == "appos":
        return "apposition"

    # Predicate complement in copular or nominal clauses.
    if dep in {"attr", "acomp", "xcomp", "ccomp", "oprd"}:
        return "complement"
    if dep == "root" and pos in {"NOUN", "PROPN", "ADJ", "PRON", "NUM"}:
        return "complement"

    # Obliques with adposition markers are PP complements.
    if dep in {"obl", "nmod", "pobj"}:
        has_case_marker = any(child.dep_.lower() == "case" for child in token.children)
        if has_case_marker:
            return "prepositional_complement"
        if morph.get("Case", "").lower() in {"dat", "acc", "gen"} and any(
            child.pos_.upper() == "ADP" for child in token.children
        ):
            return "prepositional_complement"

    if dep in {"nsubj", "csubj", "nsubj:pass", "csubj:pass"}:
        return "subject"
    if dep in {"obj", "iobj", "dobj", "pobj"}:
        return "object"
    if dep == "root" and pos in {"VERB", "AUX"}:
        return "verb"
    if pos in {"VERB", "AUX"}:
        return "verb"

    if pos in {"ADJ", "ADV", "DET", "NUM"}:
        return "modifier"
    if dep in {"amod", "advmod", "nmod", "appos", "acl", "relcl"}:
        return "modifier"

    return "other"


async def analyze_syntax(line: str) -> list[dict]:
    """Analyze syntax with odyCy and map tokens to UI syntax roles."""
    normalized_line = line.strip()
    if not normalized_line:
        return []

    cache_key = f"syntax-v4:{normalized_line}"
    cached = await get_cache(cache_key)
    if cached:
        return json.loads(cached)

    nlp = _get_odycy_model()
    if nlp is None:
        raise RuntimeError(_LOAD_ERROR or "odyCy model is unavailable")

    result: list[dict] = []
    try:
        doc = nlp(normalized_line)
        for token in doc:
            token_text = token.text.strip()
            if not token_text or token.is_punct:
                continue
            if not GREEK_TOKEN_RE.search(token_text):
                continue
            result.append(
                {"word": token_text, "role": _normalize_role(_token_role(token))}
            )
    except Exception as exc:
        raise RuntimeError(f"odyCy parsing failed: {exc}") from exc

    await set_cache(cache_key, json.dumps(result, ensure_ascii=False))
    return result
