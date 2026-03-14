import { useEffect, useMemo, useState } from 'react'
import type { DictionaryEntry } from '../../api/client'

interface LogeionTabsProps {
  entry: DictionaryEntry
}

export function LogeionTabs({ entry }: LogeionTabsProps) {
  const grouped = useMemo(() => {
    const order: string[] = []
    const bySource: Record<string, { short_def: string; long_def: string | null }[]> = {}
    for (const sense of entry.senses) {
      if (!bySource[sense.source]) {
        bySource[sense.source] = []
        order.push(sense.source)
      }
      bySource[sense.source].push({
        short_def: sense.short_def,
        long_def: sense.long_def,
      })
    }
    return { order, bySource }
  }, [entry])

  const [activeSource, setActiveSource] = useState<string>(grouped.order[0] ?? '')

  useEffect(() => {
    setActiveSource(grouped.order[0] ?? '')
  }, [entry.word, grouped.order])

  if (!grouped.order.length || !activeSource) {
    return null
  }

  const rows = grouped.bySource[activeSource] ?? []

  return (
    <div className="mt-6">
      <h3 className="text-xs font-medium tracking-wide text-red-800 dark:text-red-300 mb-3">
        Logeion (Live)
      </h3>
      <div className="flex gap-2 overflow-x-auto pb-2">
        {grouped.order.map((source) => {
          const active = source === activeSource
          return (
            <button
              key={source}
              type="button"
              onClick={() => setActiveSource(source)}
              className={`whitespace-nowrap rounded border px-2 py-1 text-xs ${
                active
                  ? 'border-slate-700 bg-slate-700 text-white'
                  : 'border-slate-300 bg-white text-slate-700'
              }`}
            >
              {source}
            </button>
          )
        })}
      </div>

      <div className="mt-3 rounded border border-slate-200">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="text-left py-2 px-3 text-xs font-medium text-slate-500">Definition</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((sense, idx) => (
              <tr key={idx} className="border-b border-slate-100 last:border-b-0">
                <td className="py-3 px-3 align-top">
                  {sense.long_def ? (
                    <div
                      className="lsj-entry logeion-entry font-greek"
                      dangerouslySetInnerHTML={{ __html: sense.long_def }}
                    />
                  ) : (
                    <p className="text-slate-700 leading-relaxed font-greek">{sense.short_def}</p>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
