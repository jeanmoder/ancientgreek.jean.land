import type { DictionaryEntry } from '../../api/client'

const SOURCE_LABELS: Record<string, string> = {
  lsj: 'LSJ',
  'middle-liddell': 'Middle Liddell',
  lewis: 'Lewis',
}

interface DictionaryEntryCardProps {
  entry: DictionaryEntry
  onWordClick?: (word: string) => void
}

export function DictionaryEntryCard({ entry, onWordClick }: DictionaryEntryCardProps) {
  return (
    <div className="py-4 border-b border-slate-100 last:border-b-0">
      <div className="mb-2 flex items-baseline gap-2">
        {onWordClick ? (
          <button
            type="button"
            onClick={() => onWordClick(entry.word)}
            className="text-base text-slate-900 font-greek underline hover:text-slate-700 underline-offset-2 cursor-pointer"
          >
            {entry.word}
          </button>
        ) : (
          <p className="text-base text-slate-900 font-greek">{entry.word}</p>
        )}
        {entry.transliteration && (
          <span className="text-xs text-slate-400 italic">{entry.transliteration}</span>
        )}
      </div>

      <div className="space-y-3">
        {entry.senses.map((sense, idx) => (
          <div key={idx}>
            <div className="flex items-baseline gap-2 mb-1">
              <span className="text-[10px] font-medium tracking-wider text-red-800 dark:text-red-300">
                {SOURCE_LABELS[sense.source] ?? sense.source}
              </span>
            </div>
            <p className="text-sm text-slate-700 leading-relaxed">{sense.short_def}</p>
            {sense.long_def && (
              <div
                className="lsj-entry mt-3"
                dangerouslySetInnerHTML={{ __html: sense.long_def }}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
