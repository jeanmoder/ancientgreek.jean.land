"""Transliterate polytonic Ancient Greek to a romanized form using scholarly conventions."""

import unicodedata

# Digraph mappings (Greek cluster -> Roman) - checked before single-char mappings
_DIGRAPHS: dict[str, str] = {
    "γγ": "ng",
    "γκ": "nk",
    "γξ": "nx",
    "γχ": "nch",
    "αι": "ai",
    "ει": "ei",
    "οι": "oi",
    "αυ": "au",
    "ευ": "eu",
    "ου": "ou",
    "ηυ": "ēu",
    "Αι": "Ai",
    "Ει": "Ei",
    "Οι": "Oi",
    "Αυ": "Au",
    "Ευ": "Eu",
    "Ου": "Ou",
    "Ηυ": "Ēu",
    "ΑΙ": "AI",
    "ΕΙ": "EI",
    "ΟΙ": "OI",
    "ΑΥ": "AU",
    "ΕΥ": "EU",
    "ΟΥ": "OU",
    "ΗΥ": "ĒU",
}

# Single-char mappings (base Greek letter -> Roman)
_LOWER_MAP: dict[str, str] = {
    "α": "a",
    "β": "b",
    "γ": "g",
    "δ": "d",
    "ε": "e",
    "ζ": "z",
    "η": "ē",
    "θ": "th",
    "ι": "i",
    "κ": "k",
    "λ": "l",
    "μ": "m",
    "ν": "n",
    "ξ": "x",
    "ο": "o",
    "π": "p",
    "ρ": "r",
    "σ": "s",
    "ς": "s",
    "τ": "t",
    "υ": "y",
    "φ": "ph",
    "χ": "ch",
    "ψ": "ps",
    "ω": "ō",
}

_UPPER_MAP: dict[str, str] = {
    k.upper(): v.upper() if len(v) == 1 else v[0].upper() + v[1:]
    for k, v in _LOWER_MAP.items()
    if k not in ("ς",)
}

_ALL_SINGLE: dict[str, str] = {**_LOWER_MAP, **_UPPER_MAP}

# Unicode combining code points for rough breathing
_ROUGH_BREATHING = "\u0314"  # COMBINING REVERSED COMMA ABOVE


def _strip_to_base_and_breathing(
    text: str,
) -> tuple[str, set[int]]:
    """Decompose Greek text to base letters and rough-breathing positions.

    Uses NFD to split accented characters into base + combining marks.
    Tracks which output positions carry rough breathing, then strips
    all combining marks.
    """
    decomposed = unicodedata.normalize("NFD", text)

    result_chars: list[str] = []
    rough_positions: set[int] = set()
    current_base_idx = -1

    for ch in decomposed:
        cat = unicodedata.category(ch)
        if cat.startswith("M"):
            # Combining mark - check for rough breathing
            if ch == _ROUGH_BREATHING and current_base_idx >= 0:
                rough_positions.add(current_base_idx)
            # Skip all combining marks (accents, breathings, iota subscript, etc.)
        else:
            result_chars.append(ch)
            current_base_idx = len(result_chars) - 1

    return "".join(result_chars), rough_positions


def transliterate(greek: str) -> str:
    """Convert polytonic Greek text to a romanized transliteration.

    Handles diphthongs, double-gamma clusters, rough breathing (-> 'h' prefix),
    and strips accents/smooth breathing/iota subscript.
    """
    if not greek:
        return ""

    base, rough_positions = _strip_to_base_and_breathing(greek)

    result: list[str] = []
    i = 0
    n = len(base)

    while i < n:
        # Try digraphs first (length 2)
        if i + 1 < n:
            pair = base[i] + base[i + 1]
            if pair in _DIGRAPHS:
                roman = _DIGRAPHS[pair]
                # Rough breathing on the first character of a digraph
                if i in rough_positions:
                    roman = "h" + roman
                result.append(roman)
                i += 2
                continue

        ch = base[i]
        if ch in _ALL_SINGLE:
            roman = _ALL_SINGLE[ch]
            if i in rough_positions:
                # For uppercase with rough breathing, put H before
                if ch.isupper():
                    roman = "H" + roman
                else:
                    roman = "h" + roman
            result.append(roman)
        else:
            # Pass through non-Greek characters (spaces, punctuation, etc.)
            result.append(ch)
        i += 1

    return "".join(result)
