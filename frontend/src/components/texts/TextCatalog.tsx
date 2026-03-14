import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchCatalog } from '../../api/client'
import type { TextInfo } from '../../api/client'
import { useAppStore } from '../../stores/appStore'
import { formatTextDisplayTitle } from './titleDisplay'

function authorGroupLabel(text: TextInfo): string {
  const id = (text.id || '').toLowerCase()
  const author = (text.author || '').trim()
  const authorLower = author.toLowerCase()

  if (id.startsWith('new-testament-') || id.startsWith('septuaginta-')) {
    return 'Bible (Greek)'
  }
  if (!author || authorLower === 'anonymous' || authorLower === 'anon.' || authorLower === 'unknown') {
    return 'Anonymous / Unattributed'
  }
  return author
}

function groupByAuthor(texts: TextInfo[]): Map<string, TextInfo[]> {
  const groups = new Map<string, TextInfo[]>()
  for (const text of texts) {
    const label = authorGroupLabel(text)
    const existing = groups.get(label)
    if (existing) existing.push(text)
    else groups.set(label, [text])
  }
  return groups
}

export function TextCatalog() {
  const setSelectedTextId = useAppStore((s) => s.setSelectedTextId)
  const setSelectedBook = useAppStore((s) => s.setSelectedBook)

  const [catalog, setCatalog] = useState<TextInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const [openAuthors, setOpenAuthors] = useState<Record<string, boolean>>({})

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchCatalog()
      .then((data) => {
        if (!cancelled) {
          setCatalog(data)
          setLoading(false)
          const initial: Record<string, boolean> = {}
          for (const t of data.slice(0, 8)) {
            initial[authorGroupLabel(t)] = true
          }
          setOpenAuthors(initial)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load catalog')
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const filtered = useMemo(() => {
    if (!filter.trim()) return catalog
    const q = filter.toLowerCase()
    return catalog.filter(
      (t) =>
        (t.tei_title ?? '').toLowerCase().includes(q) ||
        t.title.toLowerCase().includes(q) ||
        t.author.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        (t.year ?? '').toLowerCase().includes(q) ||
        (t.dialect ?? '').toLowerCase().includes(q) ||
        (t.source_corpus ?? '').toLowerCase().includes(q) ||
        (t.source_repo ?? '').toLowerCase().includes(q),
    )
  }, [catalog, filter])

  const grouped = useMemo(() => groupByAuthor(filtered), [filtered])

  useEffect(() => {
    if (!filter.trim()) return
    const next: Record<string, boolean> = {}
    for (const author of grouped.keys()) next[author] = true
    setOpenAuthors(next)
  }, [filter, grouped])

  const handleSelect = useCallback(
    (id: string) => {
      setSelectedBook(1)
      setSelectedTextId(id)
    },
    [setSelectedBook, setSelectedTextId],
  )

  const retry = useCallback(() => {
    setLoading(true)
    setError(null)
    fetchCatalog()
      .then((data) => {
        setCatalog(data)
        setLoading(false)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Failed to load catalog')
        setLoading(false)
      })
  }, [])

  if (loading) return <p className="text-sm text-slate-500">Loading catalog...</p>

  if (error) {
    return (
      <div>
        <p className="text-sm text-red-500">{error}</p>
        <button type="button" onClick={retry} className="mt-2 text-sm cursor-pointer">
          retry
        </button>
      </div>
    )
  }

  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-semibold mb-2">Texts</h1>
      <p className="text-sm text-red-800 dark:text-red-300 mb-5">
        Metadata shown where available from TEI headers; dialect is inferred where explicit markup is absent.
      </p>

      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter by TEI title, title, author, year, dialect, or corpus..."
        className="w-full border-b border-slate-300 dark:border-slate-700 py-2 mb-6 bg-transparent text-slate-800 dark:text-slate-100 placeholder:text-slate-500 dark:placeholder:text-slate-400 focus:outline-none"
      />

      {grouped.size === 0 && <p className="text-slate-500 italic">No texts match your search.</p>}

      {Array.from(grouped.entries()).map(([author, texts]) => {
        const isOpen = !!openAuthors[author]
        return (
          <div key={author} className="mb-4">
            <button
              type="button"
              onClick={() => setOpenAuthors((prev) => ({ ...prev, [author]: !isOpen }))}
              className="text-base font-semibold cursor-pointer"
            >
              {isOpen ? '▾' : '▸'} {author}
            </button>
            {isOpen && (
              <div className="mt-2 space-y-1 pl-5">
                {texts.map((text) => (
                  <div key={text.id} className="text-sm">
                    <button
                      type="button"
                      onClick={() => handleSelect(text.id)}
                      className="text-left cursor-pointer hover:text-red-800 dark:hover:text-red-300"
                      title={text.description}
                    >
                      <span>{formatTextDisplayTitle(text.title, text.tei_title)}</span>
                      {text.dialect && (
                        <span className="text-red-800/55 dark:text-red-300/55">{` (${text.dialect})`}</span>
                      )}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
