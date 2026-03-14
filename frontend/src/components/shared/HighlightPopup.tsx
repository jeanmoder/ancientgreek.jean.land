import { useEffect, useState } from 'react'
import { useTextSelection } from '../../hooks/useTextSelection'
import { useAppStore } from '../../stores/appStore'
import { fullLookup, parseText, translateText } from '../../api/client'
import type { FullLookupResult, ParseTextResult, TranslateResult } from '../../api/client'
import { GreekText } from './GreekText'

const POS_COLORS: Record<string, string> = {
  noun: 'text-blue-700 bg-blue-50',
  verb: 'text-green-700 bg-green-50',
  adjective: 'text-purple-700 bg-purple-50',
  adverb: 'text-amber-700 bg-amber-50',
  preposition: 'text-rose-700 bg-rose-50',
  conjunction: 'text-teal-700 bg-teal-50',
  article: 'text-cyan-700 bg-cyan-50',
  pronoun: 'text-indigo-700 bg-indigo-50',
  participle: 'text-emerald-700 bg-emerald-50',
  particle: 'text-orange-700 bg-orange-50',
}

const DETAIL_LABELS: Record<string, string> = {
  case: 'Case',
  num: 'Number',
  gend: 'Gender',
  tense: 'Tense',
  voice: 'Voice',
  mood: 'Mood',
  pers: 'Person',
  comp: 'Comparison',
  dial: 'Dialect',
  decl: 'Declension',
}

const PROMINENT_KEYS = new Set(['case', 'tense', 'mood', 'voice', 'decl', 'gend', 'num'])
const GREEK_TOKEN_RE = /[\u0370-\u03FF\u1F00-\u1FFF]+/g

function getPosColor(pos: string): string {
  const lower = pos.toLowerCase()
  for (const [key, color] of Object.entries(POS_COLORS)) {
    if (lower.includes(key)) return color
  }
  return 'text-slate-600 bg-slate-50'
}

function sourceAbbrev(source: string): string {
  const low = source.toLowerCase()
  if (low.includes('lsj')) return 'LSJ'
  if (low.includes('middle-liddell') || low.includes('middleliddell')) return 'ML'
  if (low.includes('autenrieth')) return 'AUT'
  if (low.includes('slater')) return 'SL'
  const letters = source.replace(/[^a-z0-9]/gi, '')
  return (letters.slice(0, 3) || source.slice(0, 3)).toUpperCase()
}

export function HighlightPopup() {
  const { selection, clearSelection } = useTextSelection()
  const setActiveTab = useAppStore((s) => s.setActiveTab)
  const setDictionaryQuery = useAppStore((s) => s.setDictionaryQuery)

  const [wordResult, setWordResult] = useState<FullLookupResult | null>(null)
  const [morphResult, setMorphResult] = useState<FullLookupResult | null>(null)
  const [parsedText, setParsedText] = useState<ParseTextResult | null>(null)
  const [translation, setTranslation] = useState<TranslateResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [morphLoading, setMorphLoading] = useState(false)
  const [popupTab, setPopupTab] = useState<'results' | 'morphology'>('results')
  const [panelRight, setPanelRight] = useState(24)

  const isMultiWord = selection ? selection.text.trim().includes(' ') : false

  useEffect(() => {
    if (!selection) {
      setWordResult(null)
      setMorphResult(null)
      setParsedText(null)
      setTranslation(null)
      setPopupTab('results')
      setMorphLoading(false)
      return
    }

    const text = selection.text.trim()
    if (!text) return

    let cancelled = false
    setLoading(true)
    setWordResult(null)
    setMorphResult(null)
    setParsedText(null)
    setTranslation(null)
    setPopupTab('results')
    setMorphLoading(false)

    if (text.includes(' ')) {
      Promise.allSettled([parseText(text, selection.parseContext ?? {}), translateText(text)])
        .then((results) => {
          if (cancelled) return

          const parseResult = results[0]
          if (parseResult.status === 'fulfilled') {
            setParsedText(parseResult.value)
          }

          const translationResult = results[1]
          if (translationResult.status === 'fulfilled') {
            setTranslation(translationResult.value)
          }

          setLoading(false)
        })
        .catch(() => {
          if (!cancelled) setLoading(false)
        })
    } else {
      fullLookup(text, selection.parseContext ?? {})
        .then((data) => {
          if (!cancelled) {
            setWordResult(data)
            setMorphResult(data)
            setLoading(false)
          }
        })
        .catch(() => {
          if (!cancelled) setLoading(false)
        })
    }

    return () => {
      cancelled = true
    }
  }, [selection])

  useEffect(() => {
    const updatePosition = () => {
      const readerPanel = document.querySelector<HTMLElement>('[data-reader-panel]')
      if (!readerPanel) {
        setPanelRight(24)
        return
      }
      const rect = readerPanel.getBoundingClientRect()
      setPanelRight(Math.max(12, window.innerWidth - rect.right))
    }
    updatePosition()
    window.addEventListener('resize', updatePosition)
    return () => window.removeEventListener('resize', updatePosition)
  }, [selection])

  if (!selection) return null

  const handleFullLookup = () => {
    setDictionaryQuery(selection.text)
    setActiveTab('dictionary')
    clearSelection()
  }

  const handleShowMorphology = () => {
    void (async () => {
      const tokens = selection.text.match(GREEK_TOKEN_RE)
      const query = tokens && tokens.length > 0 ? tokens[0] : selection.text
      setPopupTab('morphology')

      if (morphResult && morphResult.word === query) return
      if (wordResult && wordResult.word === query) {
        setMorphResult(wordResult)
        return
      }

      setMorphLoading(true)
      try {
        const data = await fullLookup(query, selection.parseContext ?? {})
        setMorphResult(data)
      } catch {
        setMorphResult(null)
      } finally {
        setMorphLoading(false)
      }
    })()
  }

  const handleLookupWord = (word: string) => {
    setDictionaryQuery(word)
    setActiveTab('dictionary')
    clearSelection()
  }

  const viewportPadding = 12
  const popupWidth = Math.min(340, Math.max(220, window.innerWidth - viewportPadding * 2))
  const maxRight = Math.max(
    viewportPadding,
    window.innerWidth - viewportPadding - popupWidth,
  )
  const popupRight = Math.min(Math.max(viewportPadding, panelRight), maxRight)
  const popupTop = Math.max(
    viewportPadding,
    Math.min(selection.y, window.innerHeight - viewportPadding - 220),
  )
  const popupMaxHeight = Math.max(220, window.innerHeight - popupTop - viewportPadding)

  const popupStyle: React.CSSProperties = {
    position: 'fixed',
    right: `${popupRight}px`,
    top: `${popupTop}px`,
    transform: 'none',
    zIndex: 9999,
    width: `${popupWidth}px`,
  }

  return (
    <div data-highlight-popup style={popupStyle}>
      <div
        className="overflow-y-auto border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-sm"
        style={{ maxHeight: `${popupMaxHeight}px` }}
      >
        {/* Header */}
        <div className="px-4 py-2.5 border-b border-slate-100">
          <div className="flex items-center justify-between gap-3">
            <GreekText className="!text-base font-medium text-slate-900 truncate">
              {selection.text.length > 60 ? selection.text.slice(0, 60) + '\u2026' : selection.text}
            </GreekText>
            <span
              onClick={clearSelection}
              className="text-slate-600 dark:text-slate-300 hover:text-red-800 dark:hover:text-red-300 text-xs cursor-pointer"
            >
              ×
            </span>
          </div>
          {wordResult?.citation_form && !isMultiWord && (
            <p className="text-xs text-slate-500 mt-0.5">
              <GreekText className="!text-xs !text-slate-500">{wordResult.citation_form}</GreekText>
            </p>
          )}
          {wordResult?.transliteration && !isMultiWord && (
            <p className="text-xs text-slate-500 italic mt-0.5">{wordResult.transliteration}</p>
          )}
        </div>

        {/* Loading */}
        {loading && (
          <div className="px-4 py-3 text-xs text-slate-500">
            {isMultiWord ? 'Parsing and translating...' : 'Looking up...'}
          </div>
        )}

        {popupTab === 'results' && parsedText && !loading && (
          <div className="px-4 py-3 space-y-2 max-h-56 overflow-y-auto border-b border-slate-100">
            {parsedText.tokens.map((tokenResult, idx) => {
              const top = tokenResult.parses[0] ?? tokenResult.top_parse
              const second = tokenResult.parses[1]
              const showSecond =
                top?.parse_pct != null &&
                second?.parse_pct != null &&
                (top.parse_pct - second.parse_pct) < 20
              const displayedParses = top ? (showSecond && second ? [top, second] : [top]) : []

              return (
              <div key={idx} className="text-xs">
                <div className="mb-1">
                  <button
                    type="button"
                    onClick={() => handleLookupWord(tokenResult.top_parse?.lemma || tokenResult.token)}
                    className="hover:opacity-80 cursor-pointer"
                  >
                    <GreekText className="!text-xs font-semibold">{tokenResult.token}</GreekText>
                  </button>
                </div>
                {tokenResult.transliteration && (
                  <p className="text-[10px] text-slate-500 italic mb-1">{tokenResult.transliteration}</p>
                )}
                {displayedParses.length === 0 && <span className="text-slate-500">No parse</span>}
                <div className="space-y-1">
                  {displayedParses.map((parse, parseIdx) => (
                    <div key={parse.signature || `${idx}-${parseIdx}`} className="flex items-center gap-1.5 flex-wrap">
                      <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${getPosColor(parse.part_of_speech)}`}>
                        {parse.part_of_speech}
                      </span>
                      <GreekText className="!text-xs text-slate-700">{parse.lemma}</GreekText>
                      {parse.parse_pct != null && (
                        <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600">
                          {parse.parse_pct.toFixed(1)}%
                        </span>
                      )}
                      {parse.analysis_label && (
                        <span className="text-[10px] text-slate-500">
                          {parse.analysis_label}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
                {(tokenResult.gloss_items?.length || tokenResult.glosses.length > 0) && (
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {(tokenResult.gloss_items && tokenResult.gloss_items.length > 0
                      ? tokenResult.gloss_items
                      : tokenResult.glosses.map((text) => ({ text, source: 'DEF' }))
                    ).map((item, glossIdx) => (
                      <span key={`${item.source}-${item.text}-${glossIdx}`} className="inline-flex items-center gap-1">
                        <button
                          type="button"
                          disabled
                          className="rounded border border-slate-200 bg-slate-50 px-1 py-0 text-[9px] leading-4 text-slate-400"
                        >
                          {item.source}
                        </button>
                        <span className="text-[10px] text-slate-600 leading-snug">{item.text}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
              )
            })}
          </div>
        )}

        {/* Translation result */}
        {popupTab === 'results' && translation && !loading && (
          <div className="px-4 py-3">
            <p className="text-xs text-slate-500 mb-1">Translation</p>
            <p className="text-sm text-slate-800 leading-relaxed">{translation.translation}</p>
          </div>
        )}

        {/* Word lookup result */}
        {popupTab === 'results' && wordResult && !loading && (
          <div className="px-4 py-3 space-y-2 max-h-72 overflow-y-auto">
            {/* Definitions */}
            {wordResult.definitions.length > 0 && (
              <div>
                {wordResult.definitions.map((def, i) => (
                  <div key={i} className="text-sm text-slate-800 mb-1.5">
                    <button
                      type="button"
                      onClick={() => handleLookupWord(def.word)}
                      className="hover:opacity-80 cursor-pointer"
                    >
                      <GreekText className="!text-sm font-medium">{def.word}</GreekText>
                    </button>
                    <div className="mt-0.5 space-y-1">
                      {def.senses.slice(0, 3).map((sense, senseIdx) => (
                        <div key={`${sense.source}-${senseIdx}`} className="inline-flex items-center gap-1.5 mr-2">
                          <button
                            type="button"
                            disabled
                            className="rounded border border-slate-200 bg-slate-50 px-1 py-0 text-[9px] leading-4 text-slate-400"
                          >
                            {sourceAbbrev(sense.source)}
                          </button>
                          <span className="text-xs text-slate-700">{sense.short_def}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Morphology parses */}
            {wordResult.parses.length > 0 && (
              <div className="space-y-1.5 border-t border-slate-100 pt-2">
                {wordResult.parses.map((parse, i) => {
                  const details = Object.entries(parse.details).filter(
                    ([, v]) => v && v.length > 0,
                  )
                  const prominent = details.filter(([k]) => PROMINENT_KEYS.has(k))
                  const regular = details.filter(([k]) => !PROMINENT_KEYS.has(k))
                  return (
                    <div key={i} className="text-xs">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <GreekText className="!text-xs font-semibold">{parse.lemma}</GreekText>
                        {parse.transliteration && (
                          <span className="text-[10px] text-slate-500 italic">{parse.transliteration}</span>
                        )}
                        <span
                          className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${getPosColor(parse.part_of_speech)}`}
                        >
                          {parse.part_of_speech}
                        </span>
                        {parse.parse_pct != null && (
                          <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600">
                            {parse.parse_pct.toFixed(1)}%
                          </span>
                        )}
                        {prominent.map(([key, value]) => (
                          <span
                            key={key}
                            className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-800"
                          >
                            <span className="font-bold text-indigo-500">
                              {DETAIL_LABELS[key] ?? key}:{' '}
                            </span>
                            {value}
                          </span>
                        ))}
                        {regular.map(([key, value]) => (
                          <span
                            key={key}
                            className="rounded bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-600"
                          >
                            <span className="font-medium text-slate-400">
                              {DETAIL_LABELS[key] ?? key}:{' '}
                            </span>
                            {value}
                          </span>
                        ))}
                        {parse.analysis_label && (
                          <span className="text-[10px] text-slate-500">
                            {parse.analysis_label}
                          </span>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}

            {/* No results */}
            {wordResult.parses.length === 0 && wordResult.definitions.length === 0 && (
              <p className="text-sm text-slate-500">No results found</p>
            )}
          </div>
        )}

        {popupTab === 'morphology' && (
          <div className="px-4 py-3 space-y-3 max-h-[68vh] overflow-y-auto border-b border-slate-100">
            {morphLoading && <p className="text-xs text-slate-500">Loading morphology...</p>}
            {!morphLoading && morphResult && (
              <>
                {morphResult.parses.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs text-slate-500">Morphology parses</p>
                    {morphResult.parses.map((parse, i) => (
                      <div key={parse.signature || i} className="text-xs border-b border-slate-100 pb-2 last:border-b-0">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <GreekText className="!text-xs font-semibold">{parse.lemma}</GreekText>
                          <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${getPosColor(parse.part_of_speech)}`}>
                            {parse.part_of_speech}
                          </span>
                          {parse.parse_pct != null && (
                            <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600">
                              {parse.parse_pct.toFixed(1)}%
                            </span>
                          )}
                        </div>
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {Object.entries(parse.details)
                            .filter(([, value]) => value && value.length > 0)
                            .map(([key, value]) => (
                              <span key={key} className="rounded bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-600">
                                <span className="font-medium text-slate-500">{DETAIL_LABELS[key] ?? key}:</span>{' '}
                                {value}
                              </span>
                            ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {morphResult.paradigms.length > 0 ? (
                  <div className="space-y-3">
                    <p className="text-xs text-slate-500">Morphology tables</p>
                    {morphResult.paradigms.map((table, tableIdx) => (
                      <div key={tableIdx}>
                        <p className="text-[11px] text-slate-600 mb-1">{table.title}</p>
                        <table className="w-full text-[11px]">
                          <thead>
                            <tr className="border-b border-slate-200">
                              {table.headers.map((h, i) => (
                                <th key={i} className="text-left py-1 pr-2 text-slate-500 font-medium">
                                  {h}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {table.rows.map((row, i) => (
                              <tr key={i} className="border-b border-slate-50">
                                {row.map((cell, j) => (
                                  <td
                                    key={j}
                                    className={`py-1 pr-2 ${j === 0 ? 'text-slate-500' : 'font-greek text-slate-700'}`}
                                  >
                                    {cell}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {table.note && (
                          <p className="mt-1 text-[10px] text-slate-500 italic">
                            Note: {table.note}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">No morphology table available for this form.</p>
                )}
              </>
            )}
            {!morphLoading && !morphResult && (
              <p className="text-xs text-slate-500">No morphology available for this selection.</p>
            )}
          </div>
        )}

        {/* Actions (word-only) */}
        {!isMultiWord && (
          <div className="flex border-t border-slate-100">
            <span
              onClick={handleFullLookup}
              className="flex-1 px-3 py-2 text-xs text-center text-slate-500 hover:text-slate-700 hover:bg-slate-50 cursor-pointer transition-colors"
            >
              Full lookup
            </span>
            <span
              onClick={popupTab === 'morphology' ? () => setPopupTab('results') : handleShowMorphology}
              className="flex-1 px-3 py-2 text-xs text-center text-slate-500 hover:text-slate-700 hover:bg-slate-50 cursor-pointer transition-colors border-l border-slate-100"
            >
              {popupTab === 'morphology' ? 'Show parsing' : 'Show morphology'}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
