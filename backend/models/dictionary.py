from pydantic import BaseModel


class MorphologyParse(BaseModel):
    form: str
    lemma: str
    part_of_speech: str
    details: dict[str, str]
    transliteration: str = ""
    signature: str = ""
    parse_pct: float | None = None
    analysis_label: str = ""


class MorphologyResult(BaseModel):
    word: str
    parses: list[MorphologyParse]


class DictionarySense(BaseModel):
    source: str  # "lsj", "middle-liddell", "autenrieth", "slater", ...
    short_def: str
    long_def: str | None = None


class DictionaryEntry(BaseModel):
    word: str
    transliteration: str = ""
    senses: list[DictionarySense]
    matched_by: str = "headword"  # "headword" | "english"
    score: float = 0.0
