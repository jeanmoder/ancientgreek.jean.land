import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

type Block =
  | { type: 'h'; level: number; text: string }
  | { type: 'p'; text: string }
  | { type: 'img'; alt: string; src: string }
  | { type: 'ul'; items: string[] }

function resolveAboutUrl(url: string): string {
  if (!url) return url
  if (/^(https?:\/\/|mailto:|#)/i.test(url)) return url
  if (url.startsWith('/')) return url
  const base = (import.meta.env.BASE_URL || '/').replace(/\/+$/, '/')
  const clean = url.replace(/^\.\//, '')
  return `${base}${clean}`
}

function pushTextWithUrls(nodes: ReactNode[], text: string, keyPrefix: string): void {
  const urlRe = /(https?:\/\/[^\s)]+|www\.[^\s)]+)/g
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = urlRe.exec(text)) !== null) {
    if (m.index > last) {
      nodes.push(text.slice(last, m.index))
    }
    const raw = m[1]
    const href = raw.startsWith('http') ? raw : `https://${raw}`
    nodes.push(
      <a
        key={`${keyPrefix}-u-${i}`}
        href={resolveAboutUrl(href)}
        target="_blank"
        rel="noreferrer"
        className="text-red-800 dark:text-red-300 hover:underline"
      >
        {raw}
      </a>,
    )
    last = urlRe.lastIndex
    i += 1
  }
  if (last < text.length) {
    nodes.push(text.slice(last))
  }
}

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const re = /\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)]+)\)/g
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      pushTextWithUrls(nodes, text.slice(last, m.index), `${keyPrefix}-t-${i}`)
    }
    if (m[1]) {
      nodes.push(
        <strong key={`${keyPrefix}-b-${i}`} className="font-semibold text-slate-800 dark:text-slate-100">
          {m[1]}
        </strong>,
      )
    } else if (m[2] && m[3]) {
      const href = resolveAboutUrl(m[3])
      const external = /^https?:\/\//i.test(href)
      nodes.push(
        <a
          key={`${keyPrefix}-a-${i}`}
          href={href}
          target={external ? '_blank' : undefined}
          rel={external ? 'noreferrer' : undefined}
          className="text-red-800 dark:text-red-300 hover:underline"
        >
          {m[2]}
        </a>,
      )
    }
    last = re.lastIndex
    i += 1
  }
  if (last < text.length) {
    pushTextWithUrls(nodes, text.slice(last), `${keyPrefix}-t-tail`)
  }
  return nodes
}

function parseMarkdown(md: string): Block[] {
  const lines = md.replace(/\r\n/g, '\n').split('\n')
  const out: Block[] = []
  const paraBuf: string[] = []
  let listBuf: string[] = []

  const flushPara = () => {
    if (paraBuf.length) {
      out.push({ type: 'p', text: paraBuf.join(' ').trim() })
      paraBuf.length = 0
    }
  }
  const flushList = () => {
    if (listBuf.length) {
      out.push({ type: 'ul', items: listBuf })
      listBuf = []
    }
  }

  for (const raw of lines) {
    const line = raw.trimEnd()
    if (!line.trim()) {
      flushPara()
      flushList()
      continue
    }

    const h = line.match(/^(#{1,6})\s+(.*)$/)
    if (h) {
      flushPara()
      flushList()
      out.push({ type: 'h', level: h[1].length, text: h[2].trim() })
      continue
    }

    const li = line.match(/^\s*[*-]\s+(.*)$/)
    if (li) {
      flushPara()
      listBuf.push(li[1].trim())
      continue
    }

    const img = line.match(/^!\[([^\]]*)\]\(([^)]+)\)$/)
    if (img) {
      flushPara()
      flushList()
      out.push({ type: 'img', alt: img[1].trim(), src: img[2].trim() })
      continue
    }

    flushList()
    paraBuf.push(line.trim())
  }

  flushPara()
  flushList()
  return out
}

export function AboutPage() {
  const [markdown, setMarkdown] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch('/about.md')
      .then((r) => {
        if (!r.ok) throw new Error(`Failed to load about.md (${r.status})`)
        return r.text()
      })
      .then((text) => {
        if (!cancelled) {
          setMarkdown(text)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load about page')
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const blocks = useMemo(() => parseMarkdown(markdown), [markdown])

  if (loading) return <p className="text-sm text-slate-500">Loading about...</p>
  if (error) return <p className="text-sm text-red-500">{error}</p>

  return (
    <article className="max-w-3xl space-y-4 text-sm leading-relaxed text-slate-700 dark:text-slate-300 [&_a]:text-red-800 [&_a]:dark:text-red-300 [&_a]:underline [&_a]:underline-offset-2">
      {blocks.map((b, i) => {
        if (b.type === 'h') {
          if (b.level === 1) {
            return (
              <h1 key={i} className="text-3xl font-semibold text-slate-900 dark:text-slate-100">
                {renderInline(b.text, `h1-${i}`)}
              </h1>
            )
          }
          return (
            <h2 key={i} className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              {renderInline(b.text, `h2-${i}`)}
            </h2>
          )
        }
        if (b.type === 'ul') {
          return (
            <ul key={i} className="list-disc pl-5 space-y-1">
              {b.items.map((item, j) => (
                <li key={`${i}-${j}`}>{renderInline(item, `li-${i}-${j}`)}</li>
              ))}
            </ul>
          )
        }
        if (b.type === 'img') {
          return (
            <figure key={i} className="rounded-lg border border-slate-200 dark:border-slate-800 p-2 bg-white/60 dark:bg-slate-900/40">
              <img
                src={resolveAboutUrl(b.src)}
                alt={b.alt || 'about demo image'}
                loading="lazy"
                className="w-full h-auto rounded-md"
              />
              {b.alt && (
                <figcaption className="mt-2 text-xs text-slate-500 dark:text-slate-400">{b.alt}</figcaption>
              )}
            </figure>
          )
        }
        return <p key={i}>{renderInline(b.text, `p-${i}`)}</p>
      })}
    </article>
  )
}
