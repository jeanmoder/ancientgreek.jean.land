from pydantic import BaseModel


class TextInfo(BaseModel):
    id: str
    title: str
    tei_title: str | None = None
    author: str
    description: str
    urn: str
    type: str = "prose"
    year: str | None = None
    dialect: str | None = None
    source_corpus: str | None = None
    source_repo: str | None = None
    source_branch: str | None = None
    source_license: str | None = None
    source_url: str | None = None


class TextLine(BaseModel):
    n: str
    text: str


class TextPassage(BaseModel):
    text_id: str
    title: str
    tei_title: str | None = None
    author: str
    urn: str
    book_n: str
    book_label: str
    passage_ref: str
    lines: list[TextLine]


class BookInfo(BaseModel):
    n: str
    label: str
    line_count: int


class BooksResponse(BaseModel):
    books: list[BookInfo]
