import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { analyzeSyntax, fetchBooks, fetchPassage, translateText } from '../../api/client'
import type { BookInfo, SyntaxWord, TextPassage } from '../../api/client'
import { GreekText } from '../shared/GreekText'
import { useAppStore } from '../../stores/appStore'
import { formatTextDisplayTitle } from './titleDisplay'

const PAGE_SIZE = 50

const ROLE_STYLES: Record<string, string> = {
  subject: 'text-red-600 font-semibold',
  verb: 'text-green-600 font-semibold',
  object: 'text-blue-600 font-semibold',
  complement: 'text-cyan-700 font-semibold',
  prepositional_complement: 'text-violet-700 font-semibold',
  apposition: 'text-fuchsia-700 font-semibold',
  modifier: 'text-purple-600',
  particle: 'text-amber-600',
  conjunction: 'text-amber-600',
  preposition: 'text-amber-600',
  article: 'text-emerald-700',
  other: 'text-slate-600 dark:text-slate-300',
}

function splitIntoSentences(line: string): string[] {
  const parts = (line.match(/[^.!?;·;]+[.!?;·;]*/gu) ?? [line])
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
  return parts.length > 0 ? parts : [line.trim()]
}

function fallbackSyntaxWords(line: string): SyntaxWord[] {
  const words = line.match(/[\u0370-\u03FF\u1F00-\u1FFF]+/gu) ?? []
  return words.map((word) => ({ word, role: 'other' }))
}

function isGenericBookLabel(book: BookInfo): boolean {
  const label = (book.label || '').trim()
  if (!label) return true
  if (new RegExp(`^book\\s+${book.n}$`, 'i').test(label)) return true
  if (/^book\s+[0-9]+$/i.test(label)) return true
  if (/^book\s+[ivxlcdm]+$/i.test(label)) return true
  return false
}

function isSingleFullText(books: BookInfo[]): boolean {
  return books.length === 1 && /^\s*full\s*text\s*$/i.test(books[0].label || '')
}

function baseBookDisplayLabel(book: BookInfo): string {
  return isGenericBookLabel(book) ? book.n : (book.label || book.n)
}

function disambiguatedBookLabels(books: BookInfo[]): string[] {
  const totals = new Map<string, number>()
  const seen = new Map<string, number>()
  const out: string[] = []
  const bases = books.map((book) => baseBookDisplayLabel(book).trim())

  for (const base of bases) {
    const key = base.toLowerCase()
    totals.set(key, (totals.get(key) ?? 0) + 1)
  }

  for (const base of bases) {
    const key = base.toLowerCase()
    const total = totals.get(key) ?? 1
    if (total <= 1) {
      out.push(base)
      continue
    }
    if (/\b([0-9]+|[ivxlcdm]+)$/i.test(base)) {
      out.push(base)
      continue
    }
    const idx = (seen.get(key) ?? 0) + 1
    seen.set(key, idx)
    out.push(`${base} ${idx}`)
  }
  return out
}

function isLikelyHeaderLine(text: string): boolean {
  const trimmed = text.trim()
  if (!trimmed || trimmed.length > 44) return false
  const letters = Array.from(trimmed).filter((ch) => /\p{L}/u.test(ch))
  if (letters.length < 3) return false
  if (/[.!?;·;]$/.test(trimmed)) return false

  let upper = 0
  let lower = 0
  for (const ch of letters) {
    const up = ch.toLocaleUpperCase()
    const low = ch.toLocaleLowerCase()
    if (ch === up && ch !== low) upper += 1
    if (ch === low && ch !== up) lower += 1
  }
  if (lower === 0 && upper >= 3) return true
  return upper / letters.length >= 0.8
}

type SideTab = 'parsing' | 'translation'

export function TextReader() {
  const selectedTextId = useAppStore((s) => s.selectedTextId)
  const setSelectedTextId = useAppStore((s) => s.setSelectedTextId)
  const selectedBook = useAppStore((s) => s.selectedBook)
  const setSelectedBook = useAppStore((s) => s.setSelectedBook)
  const setSyntaxLegendVisible = useAppStore((s) => s.setSyntaxLegendVisible)

  const [books, setBooks] = useState<BookInfo[]>([])
  const [passage, setPassage] = useState<TextPassage | null>(null)
  const [loading, setLoading] = useState(true)
  const [booksLoading, setBooksLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [start, setStart] = useState(1)

  const [syntaxData, setSyntaxData] = useState<Record<string, SyntaxWord[]>>({})
  const [syntaxLoading, setSyntaxLoading] = useState<Record<string, boolean>>({})
  const [panelLineN, setPanelLineN] = useState<string | null>(null)
  const [panelLineText, setPanelLineText] = useState('')
  const [panelTab, setPanelTab] = useState<SideTab>('parsing')
  const [panelTop, setPanelTop] = useState(0)
  const [panelMaxHeight, setPanelMaxHeight] = useState(420)
  const [panelTranslations, setPanelTranslations] = useState<Record<string, string>>({})
  const [panelTranslationLoading, setPanelTranslationLoading] = useState<Record<string, boolean>>({})
  const textPanelRef = useRef<HTMLDivElement | null>(null)

  const end = start + PAGE_SIZE - 1

  useEffect(() => {
    if (!selectedTextId) return
    let cancelled = false
    setBooksLoading(true)
    fetchBooks(selectedTextId)
      .then((data) => {
        if (!cancelled) {
          setBooks(data.books)
          setBooksLoading(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBooks([])
          setBooksLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [selectedTextId])

  useEffect(() => {
    if (books.length === 0) return
    if (!Number.isFinite(selectedBook) || selectedBook < 1 || selectedBook > books.length) {
      setSelectedBook(1)
    }
  }, [books, selectedBook, setSelectedBook])

  const loadPassage = useCallback(() => {
    if (!selectedTextId) return
    setLoading(true)
    setError(null)
    fetchPassage(selectedTextId, selectedBook, start, end)
      .then((data) => {
        setPassage(data)
        setLoading(false)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Failed to load passage')
        setLoading(false)
      })
  }, [selectedTextId, selectedBook, start, end])

  useEffect(() => {
    loadPassage()
  }, [loadPassage])

  useEffect(() => {
    setSyntaxData({})
    setSyntaxLoading({})
    setPanelLineN(null)
    setPanelLineText('')
    setPanelTab('parsing')
    setPanelMaxHeight(420)
    setPanelTranslations({})
    setPanelTranslationLoading({})
    setSyntaxLegendVisible(false)
  }, [selectedTextId, selectedBook, start, setSyntaxLegendVisible])

  useEffect(() => {
    setSyntaxLegendVisible(Object.keys(syntaxData).length > 0)
  }, [setSyntaxLegendVisible, syntaxData])

  const handleBack = useCallback(() => {
    setSelectedTextId(null)
    setSelectedBook(1)
    setSyntaxLegendVisible(false)
  }, [setSelectedBook, setSelectedTextId, setSyntaxLegendVisible])

  const handleBookChange = useCallback(
    (bookN: number) => {
      setSelectedBook(bookN)
      setStart(1)
    },
    [setSelectedBook],
  )

  const handlePrev = useCallback(() => {
    setStart((prev) => Math.max(1, prev - PAGE_SIZE))
  }, [])

  const handleNext = useCallback(() => {
    setStart((prev) => prev + PAGE_SIZE)
  }, [])

  const ensureTranslation = useCallback((lineN: string, lineText: string) => {
    if (panelTranslations[lineN] || panelTranslationLoading[lineN]) return
    setPanelTranslationLoading((prev) => ({ ...prev, [lineN]: true }))
    translateText(lineText)
      .then((result) => {
        setPanelTranslations((prev) => ({ ...prev, [lineN]: result.translation }))
      })
      .catch(() => {
        setPanelTranslations((prev) => ({ ...prev, [lineN]: '(Translation unavailable)' }))
      })
      .finally(() => {
        setPanelTranslationLoading((prev) => ({ ...prev, [lineN]: false }))
      })
  }, [panelTranslationLoading, panelTranslations])

  const positionSentencePanel = useCallback((anchorEl: HTMLElement | null) => {
    if (!anchorEl || !textPanelRef.current) return
    const containerRect = textPanelRef.current.getBoundingClientRect()
    const anchorRect = anchorEl.getBoundingClientRect()
    const viewportPadding = 12
    const screenTop = Math.max(
      viewportPadding,
      Math.min(anchorRect.top - 8, window.innerHeight - viewportPadding - 220),
    )
    const top = Math.max(0, screenTop - containerRect.top)
    const maxHeight = Math.max(220, window.innerHeight - screenTop - viewportPadding)
    setPanelTop(top)
    setPanelMaxHeight(maxHeight)
  }, [])

  const openSentencePanel = useCallback((lineN: string, lineText: string, anchorEl: HTMLElement | null = null) => {
    setPanelLineN(lineN)
    setPanelLineText(lineText)
    positionSentencePanel(anchorEl)
    ensureTranslation(lineN, lineText)
  }, [ensureTranslation, positionSentencePanel])

  useEffect(() => {
    if (!panelLineN || !textPanelRef.current) return
    const viewportPadding = 12
    const minPanelSpace = 220
    const recalc = () => {
      if (!textPanelRef.current) return
      const containerRect = textPanelRef.current.getBoundingClientRect()
      const currentScreenTop = containerRect.top + panelTop
      const clampedScreenTop = Math.max(
        viewportPadding,
        Math.min(currentScreenTop, window.innerHeight - viewportPadding - minPanelSpace),
      )
      const clampedTop = Math.max(0, clampedScreenTop - containerRect.top)
      setPanelTop(clampedTop)
      setPanelMaxHeight(Math.max(minPanelSpace, window.innerHeight - clampedScreenTop - viewportPadding))
    }
    recalc()
    window.addEventListener('resize', recalc)
    return () => window.removeEventListener('resize', recalc)
  }, [panelLineN, panelTop])

  const handleSyntaxToggle = useCallback(
    (lineN: string, lineText: string, anchorEl: HTMLElement | null) => {
      if (syntaxData[lineN]) {
        setSyntaxData((prev) => {
          const next = { ...prev }
          delete next[lineN]
          return next
        })
        setSyntaxLoading((prev) => {
          const next = { ...prev }
          delete next[lineN]
          return next
        })
        if (panelLineN === lineN) {
          setPanelLineN(null)
          setPanelLineText('')
        }
        return
      }

      setSyntaxLoading((prev) => ({ ...prev, [lineN]: true }))
      const sentences = splitIntoSentences(lineText)
      Promise.all(sentences.map((sentence) => analyzeSyntax(sentence)))
        .then((sentenceResults) => {
          const merged = sentenceResults.flat()
          setSyntaxData((prev) => ({ ...prev, [lineN]: merged }))
          openSentencePanel(lineN, lineText, anchorEl)
        })
        .catch(() => {
          setSyntaxData((prev) => ({ ...prev, [lineN]: fallbackSyntaxWords(lineText) }))
          openSentencePanel(lineN, lineText, anchorEl)
        })
        .finally(() => {
          setSyntaxLoading((prev) => ({ ...prev, [lineN]: false }))
        })
    },
    [openSentencePanel, panelLineN, syntaxData],
  )

  const renderSyntaxLine = useCallback((lineText: string, words: SyntaxWord[]) => {
    const segments = lineText.split(/([\u0370-\u03FF\u1F00-\u1FFF]+)/gu)
    let wordIdx = 0
    return segments.map((segment, idx) => {
      if (!segment) return null

      const isGreekWord = /^[\u0370-\u03FF\u1F00-\u1FFF]+$/u.test(segment)
      if (!isGreekWord) {
        return (
          <span key={idx} className="text-slate-700 dark:text-slate-300">
            {segment}
          </span>
        )
      }

      const role = words[wordIdx]?.role ?? 'other'
      wordIdx += 1
      return (
        <span
          key={idx}
          className={`${ROLE_STYLES[role] || ROLE_STYLES.other} relative group/word`}
          title={role}
        >
          {segment}
          <span className="invisible group-hover/word:visible absolute left-1/2 -translate-x-1/2 -top-7 px-1.5 py-0.5 text-[10px] font-medium bg-slate-800 text-white rounded whitespace-nowrap z-10 pointer-events-none select-none">
            {role}
          </span>
        </span>
      )
    })
  }, [])

  const currentBookInfo = selectedBook >= 1 && selectedBook <= books.length ? books[selectedBook - 1] : undefined
  const hideBookSelector = isSingleFullText(books)
  const selectorLabels = useMemo(() => disambiguatedBookLabels(books), [books])
  const currentBookDisplayLabel =
    selectorLabels[selectedBook - 1] ||
    passage?.book_label ||
    currentBookInfo?.label ||
    `Book ${selectedBook}`
  const totalLines = currentBookInfo?.line_count ?? 0
  const hasNextPage = totalLines > 0 ? start + PAGE_SIZE <= totalLines : true
  const displayEnd = passage ? start + passage.lines.length - 1 : end

  const panelWords = useMemo(() => {
    if (!panelLineN) return []
    return syntaxData[panelLineN] ?? []
  }, [panelLineN, syntaxData])
  const textDisplayTitle = useMemo(
    () => (passage ? formatTextDisplayTitle(passage.title, passage.tei_title) : ''),
    [passage],
  )

  if (!selectedTextId) return null

  return (
    <div className="max-w-6xl mx-auto">
      <div>
        <button onClick={handleBack} className="text-sm text-slate-500 dark:text-slate-400 hover:text-red-800 dark:hover:text-red-300 cursor-pointer mb-5">
          ← back to catalog
        </button>

        {passage && (
          <div className="mb-6">
            <h1 className="text-3xl font-semibold">{textDisplayTitle}</h1>
            <p className="text-sm text-red-800 dark:text-red-300 mt-1">{passage.author}</p>
          </div>
        )}

        {!booksLoading && books.length > 0 && !hideBookSelector && (
          <div className="mb-5 text-sm xl:pr-[360px]">
            <span className="text-red-800 dark:text-red-300 mr-2">Book:</span>
            {books.map((book, idx) => {
              const bookIndex = idx + 1
              const isActive = bookIndex === selectedBook
              const label = selectorLabels[idx] || book.label || book.n || String(bookIndex)
              return (
                <span key={`${bookIndex}-${book.n}-${book.label}`}>
                  <button
                    type="button"
                    onClick={() => handleBookChange(bookIndex)}
                    className={`cursor-pointer ${isActive ? 'text-slate-900 dark:text-slate-100 font-semibold' : 'text-slate-500 dark:text-slate-400 hover:text-red-800 dark:hover:text-red-300'}`}
                  >
                    {label}
                    <span className="ml-1 text-[11px] text-slate-400 dark:text-slate-500">· {book.line_count}</span>
                  </button>
                  {idx < books.length - 1 && <span className="mx-1 text-slate-400">·</span>}
                </span>
              )
            })}
          </div>
        )}

        {loading && <p className="text-sm text-slate-500">Loading passage...</p>}

        {error && !loading && (
          <div>
            <p className="text-red-600 text-sm">{error}</p>
            <button onClick={loadPassage} className="mt-2 text-sm text-slate-600 dark:text-slate-300 hover:text-red-800 dark:hover:text-red-300 cursor-pointer">
              retry
            </button>
          </div>
        )}

        {!loading && !error && passage && (
          <div ref={textPanelRef} data-reader-panel className="relative xl:pr-[360px]">
            <h2 className="text-lg font-semibold mb-2">
              {currentBookDisplayLabel}
              {totalLines > 0 && (
                <span className="ml-2 text-sm font-normal text-slate-400 dark:text-slate-500">
                  · {totalLines} lines
                </span>
              )}
            </h2>
            {passage.lines.length === 0 ? (
              <p className="text-slate-500 italic">No lines available for this range.</p>
            ) : (
              <table className="w-full border-collapse">
                <tbody>
                  {passage.lines.map((line) => {
                    const hasSyntax = !!syntaxData[line.n]
                    const parsedWords = syntaxData[line.n] ?? []
                    const isLoadingSyntax = !!syntaxLoading[line.n]
                    const headerLike = isLikelyHeaderLine(line.text)
                    return (
                      <tr key={line.n} className="align-top group">
                        <td className="text-xs text-slate-400 pr-3 pt-1 text-right select-none tabular-nums w-10 whitespace-nowrap" style={{ lineHeight: 2 }}>
                          {line.n}
                        </td>
                        <td
                          className="py-0 pr-2 cursor-pointer"
                          onClick={(e) => {
                            if (hasSyntax) {
                              openSentencePanel(line.n, line.text, e.currentTarget)
                            }
                          }}
                        >
                          <span data-greek-line data-perseus-d={passage.urn} className="block">
                            {hasSyntax ? (
                              <span
                                lang="grc"
                                className={`block font-greek ${headerLike ? 'text-slate-400 dark:text-slate-500 tracking-wide' : ''}`}
                                style={{
                                  lineHeight: 2,
                                  fontSize: '1.25em',
                                }}
                              >
                                {renderSyntaxLine(line.text, parsedWords)}
                              </span>
                            ) : (
                              <GreekText className={`block ${headerLike ? 'text-slate-400 dark:text-slate-500 tracking-wide' : ''}`}>
                                {line.text}
                              </GreekText>
                            )}
                          </span>
                        </td>
                        <td className="w-8 pt-1" style={{ lineHeight: 2 }}>
                          <button
                            type="button"
                            onClick={(e) => handleSyntaxToggle(line.n, line.text, e.currentTarget)}
                            disabled={isLoadingSyntax}
                            className={`text-xs cursor-pointer ${hasSyntax ? 'text-indigo-700 dark:text-indigo-300' : 'text-slate-500 dark:text-slate-300'} hover:text-red-800 dark:hover:text-red-300 ${isLoadingSyntax ? 'opacity-60' : ''}`}
                            title={hasSyntax ? 'Hide syntax coloring' : 'Show syntax coloring'}
                          >
                            {isLoadingSyntax ? '…' : 'Σ'}
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}

            <div className="flex items-center justify-between py-4 mt-2 border-t border-slate-200 dark:border-slate-800">
              <button
                type="button"
                onClick={handlePrev}
                disabled={start <= 1}
                className="text-sm disabled:text-slate-400 cursor-pointer hover:text-red-800 dark:hover:text-red-300"
              >
                ← prev {PAGE_SIZE}
              </button>
              <span className="text-sm text-slate-500 dark:text-slate-400">
                lines {start}–{displayEnd}
                {totalLines > 0 && ` of ${totalLines}`}
              </span>
              <button
                type="button"
                onClick={handleNext}
                disabled={!hasNextPage}
                className="text-sm disabled:text-slate-400 cursor-pointer hover:text-red-800 dark:hover:text-red-300"
              >
                next {PAGE_SIZE} →
              </button>
            </div>

            {panelLineN && (
              <div className="hidden xl:block absolute right-0 w-[340px]" style={{ top: panelTop }}>
                <div
                  className="overflow-y-auto border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-sm p-4"
                  style={{ maxHeight: `${panelMaxHeight}px` }}
                >
                  <div className="flex items-center justify-between text-sm mb-2">
                    <span className="text-red-800 dark:text-red-300">Sentence panel</span>
                    <button
                      type="button"
                      onClick={() => {
                        setPanelLineN(null)
                        setPanelLineText('')
                      }}
                      className="text-slate-500 dark:text-slate-300 hover:text-red-800 dark:hover:text-red-300 cursor-pointer"
                    >
                      ×
                    </button>
                  </div>
                  <div className="flex items-center gap-4 text-sm mb-2">
                    <button
                      type="button"
                      onClick={() => setPanelTab('parsing')}
                      className={`cursor-pointer ${panelTab === 'parsing' ? 'text-slate-900 dark:text-slate-100' : 'text-slate-500 dark:text-slate-400 hover:text-red-800 dark:hover:text-red-300'}`}
                    >
                      Parsing
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setPanelTab('translation')
                        ensureTranslation(panelLineN, panelLineText)
                      }}
                      className={`cursor-pointer ${panelTab === 'translation' ? 'text-slate-900 dark:text-slate-100' : 'text-slate-500 dark:text-slate-400 hover:text-red-800 dark:hover:text-red-300'}`}
                    >
                      Translation
                    </button>
                  </div>
                  <GreekText className="block mb-3 !text-base">{panelLineText}</GreekText>

                  {panelTab === 'parsing' && (
                    <div className="space-y-1.5">
                      {panelWords.map((word, idx) => (
                        <div key={`${word.word}-${idx}`} className="text-sm">
                          <span className={ROLE_STYLES[word.role] || ROLE_STYLES.other}>{word.word}</span>
                          <span className="ml-2 text-xs text-slate-500 dark:text-slate-400">{word.role}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {panelTab === 'translation' && (
                    <div>
                      <p className="text-xs text-red-800 dark:text-red-300 mb-1">
                        Translated by Gemini Flash 
                      </p>
                      {panelTranslationLoading[panelLineN] ? (
                        <p className="text-sm text-slate-500 dark:text-slate-400">Translating…</p>
                      ) : (
                        <p className="text-sm leading-relaxed">{panelTranslations[panelLineN] ?? '(Translation unavailable)'}</p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
