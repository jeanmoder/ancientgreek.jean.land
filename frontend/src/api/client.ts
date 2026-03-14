function normalizeApiBase(raw: string | undefined): string {
  const fallback = '/api'
  if (!raw || !raw.trim()) return fallback
  let base = raw.trim().replace(/\/+$/, '')
  // Common deployment misconfig: domain root provided without /api prefix.
  if (!/\/api(?:\/|$)/i.test(base)) {
    base = `${base}/api`
  }
  return base
}

const BASE_URL = normalizeApiBase(import.meta.env.VITE_API_BASE_URL as string | undefined)

export class ApiError extends Error {
  status: number
  statusText: string
  body: unknown

  constructor(status: number, statusText: string, body: unknown) {
    super(`API error ${status}: ${statusText}`)
    this.name = 'ApiError'
    this.status = status
    this.statusText = statusText
    this.body = body
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${BASE_URL}${path}`
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  }

  const response = await fetch(url, { ...options, headers })

  if (!response.ok) {
    const body = await response.text().catch(() => null)
    throw new ApiError(response.status, response.statusText, body)
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T
  }

  const contentType = (response.headers.get('content-type') ?? '').toLowerCase()
  if (contentType.includes('application/json')) {
    return response.json() as Promise<T>
  }

  const raw = await response.text().catch(() => '')
  const looksLikeHtml = /^\s*</.test(raw)
  const body = looksLikeHtml
    ? `Expected JSON from ${url} but received HTML. Check VITE_API_BASE_URL (current: ${BASE_URL}).`
    : `Expected JSON from ${url} but got content-type "${contentType || 'unknown'}".`
  throw new Error(body)
}

// ── HTTP helpers ──────────────────────────────────────────────────────

function get<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'GET' })
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
}

// ── Dictionary endpoints ──────────────────────────────────────────────

export interface MorphologyParse {
  form: string
  lemma: string
  part_of_speech: string
  details: Record<string, string>
  transliteration: string
  signature: string
  parse_pct: number | null
  analysis_label: string
}

export interface MorphologyResult {
  word: string
  parses: MorphologyParse[]
}

export interface DictionaryEntry {
  word: string
  transliteration: string
  senses: {
    source: string
    short_def: string
    long_def: string | null
  }[]
  matched_by: string
  score: number
}

export interface FullLookupResult {
  word: string
  transliteration: string
  parses: MorphologyParse[]
  preferred_parse: MorphologyParse | null
  definitions: DictionaryEntry[]
  paradigms: {
    title: string
    headers: string[]
    rows: string[][]
    note?: string | null
    source?: string
    source_url?: string
  }[]
  paradigm: {
    title: string
    headers: string[]
    rows: string[][]
    note?: string | null
    source?: string
    source_url?: string
  } | null
  citation_form: string
}

export function parseWord(word: string): Promise<MorphologyResult> {
  return get(`/dictionary/parse?word=${encodeURIComponent(word)}`)
}

export interface PerseusParseContext {
  prior?: string
  d?: string
  can?: string
  i?: number
}

export function parseWordWithContext(
  word: string,
  context: PerseusParseContext = {},
): Promise<MorphologyResult> {
  const params = new URLSearchParams({ word })
  if (context.prior) params.set('prior', context.prior)
  if (context.d) params.set('d', context.d)
  if (context.can) params.set('can', context.can)
  if (context.i !== undefined) params.set('i', String(context.i))
  return get(`/dictionary/parse?${params.toString()}`)
}

export function lookupWord(word: string): Promise<DictionaryEntry[]> {
  return get(`/dictionary/lookup?word=${encodeURIComponent(word)}`)
}

export function fullLookup(
  word: string,
  context: PerseusParseContext = {},
  options: { liveEntry?: boolean } = {},
): Promise<FullLookupResult> {
  const params = new URLSearchParams({ word })
  if (options.liveEntry) params.set('live', 'true')
  if (context.prior) params.set('prior', context.prior)
  if (context.d) params.set('d', context.d)
  if (context.can) params.set('can', context.can)
  if (context.i !== undefined) params.set('i', String(context.i))
  return get(`/dictionary/full?${params.toString()}`)
}

export interface ParsedToken {
  token: string
  transliteration: string
  glosses: string[]
  gloss_items?: { text: string; source: string }[]
  top_parse: MorphologyParse | null
  parses: MorphologyParse[]
}

export interface ParseTextResult {
  text: string
  tokens: ParsedToken[]
}

export function parseText(
  text: string,
  context: PerseusParseContext = {},
): Promise<ParseTextResult> {
  return post('/dictionary/parse-text', { text, ...context })
}

export interface TranslateResult {
  text: string
  translation: string
}

export function translateText(text: string): Promise<TranslateResult> {
  return post('/dictionary/translate', { text })
}

// ── Texts endpoints ───────────────────────────────────────────────────

export interface TextInfo {
  id: string
  title: string
  tei_title?: string | null
  author: string
  description: string
  urn: string
  type?: string
  year?: string | null
  dialect?: string | null
  source_corpus?: string | null
  source_repo?: string | null
  source_branch?: string | null
  source_license?: string | null
  source_url?: string | null
}

export interface BookInfo {
  n: string
  label: string
  line_count: number
}

export interface TextPassage {
  text_id: string
  title: string
  tei_title?: string | null
  author: string
  urn: string
  book_n: string
  book_label: string
  passage_ref: string
  lines: { n: string; text: string }[]
}

export function fetchCatalog(): Promise<TextInfo[]> {
  return get('/texts/catalog')
}

export function fetchBooks(textId: string): Promise<{ books: BookInfo[] }> {
  return get(`/texts/books/${textId}`)
}

export function fetchPassage(textId: string, book = 1, start = 1, end = 50): Promise<TextPassage> {
  return get(`/texts/read/${textId}?book=${book}&start=${start}&end=${end}`)
}

// ── Syntax endpoints ─────────────────────────────────────────────────

export interface SyntaxWord {
  word: string
  role: string
}

export function analyzeSyntax(line: string): Promise<SyntaxWord[]> {
  return post('/texts/syntax', { line })
}
