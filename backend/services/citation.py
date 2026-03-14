"""Build citation forms for Greek words.

- Nouns: lemma, gen. ending, article (e.g. "λόγος, -ου, ὁ")
- Verbs: principal parts (e.g. "λύω, λύσω, ἔλυσα, λέλυκα, λέλυμαι, ἐλύθην")
- Adjectives: masc, fem, neut endings (e.g. "δεύτερος, -α, -ον")
"""

import unicodedata


def _strip_accents(s: str) -> str:
    decomposed = unicodedata.normalize("NFD", s)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", stripped)


# Article by gender
ARTICLES = {
    "masculine": "ὁ",
    "feminine": "ἡ",
    "neuter": "τό",
    "masc": "ὁ",
    "fem": "ἡ",
    "neut": "τό",
}

# 2nd declension genitive endings
NOUN_GEN_ENDINGS: dict[str, list[tuple[str, str]]] = {
    "2nd": [("ος", "-ου"), ("ον", "-ου")],
    "1st": [("η", "-ης"), ("α", "-ας"), ("ης", "-ου"), ("ας", "-ου")],
    "3rd": [("ξ", "-κος"), ("ψ", "-πος"), ("ς", "-ος"), ("ρ", "-ρος")],
}


def build_noun_citation(lemma: str, declension: str, gender: str) -> str:
    """Build noun citation: λόγος, -ου, ὁ."""
    decl = declension.strip().lower()
    gend = gender.strip().lower()
    article = ARTICLES.get(gend, "")

    # Find genitive ending
    gen_suffix = ""
    bare = _strip_accents(lemma)
    for decl_key, endings in NOUN_GEN_ENDINGS.items():
        if decl_key in decl:
            for nom_end, gen_end in endings:
                if bare.endswith(nom_end):
                    gen_suffix = gen_end
                    break
            if gen_suffix:
                break

    parts = [lemma]
    if gen_suffix:
        parts.append(gen_suffix)
    if article:
        parts.append(article)
    return ", ".join(parts)


def build_adjective_citation(lemma: str, declension: str) -> str:
    """Build adjective citation: δεύτερος, -α, -ον."""
    bare = _strip_accents(lemma)
    if bare.endswith("ος") and ("1" in declension or "2" in declension):
        return f"{lemma}, -α, -ον"
    if bare.endswith("ης") and "3" in declension:
        return f"{lemma}, -ες"
    return lemma


def build_verb_citation(lemma: str) -> str:
    """Build verb citation with principal parts placeholder.

    Full principal parts require lexicon data; for now show the standard
    form pattern: present active, future, aorist, perfect, perfect mid/pass, aorist passive.
    """
    bare = _strip_accents(lemma)
    if not bare.endswith("ω"):
        return lemma

    stem = bare[:-1]
    # Regular -ω verb principal parts pattern (approximate)
    return (
        f"{lemma}, {stem}σω (fut.), "
        f"ἐ{stem}σα (aor.), "
        f"{stem}κα (pf.)"
    )


def build_citation(
    lemma: str,
    pos: str,
    declension: str = "",
    gender: str = "",
) -> str:
    """Build the citation form for a word based on its POS."""
    pos_lower = pos.lower()
    if "noun" in pos_lower:
        return build_noun_citation(lemma, declension, gender)
    if "adjective" in pos_lower or "adj" in pos_lower:
        return build_adjective_citation(lemma, declension)
    if "verb" in pos_lower:
        return build_verb_citation(lemma)
    return lemma
