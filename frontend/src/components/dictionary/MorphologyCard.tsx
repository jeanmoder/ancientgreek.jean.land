import type { MorphologyParse } from '../../api/client'
import { GreekText } from '../shared/GreekText'

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

const PROMINENT_KEYS = new Set(['case', 'tense', 'mood', 'voice', 'decl', 'gend', 'num', 'pers'])

function getPosColor(pos: string): string {
  const lower = pos.toLowerCase()
  for (const [key, color] of Object.entries(POS_COLORS)) {
    if (lower.includes(key)) return color
  }
  return 'text-slate-600 bg-slate-50'
}

interface MorphologyCardProps {
  parse: MorphologyParse
  onLemmaClick?: (lemma: string) => void
}

export function MorphologyCard({ parse, onLemmaClick }: MorphologyCardProps) {
  const detailEntries = Object.entries(parse.details).filter(
    ([, value]) => value && value.length > 0,
  )

  const prominentDetails = detailEntries.filter(([key]) => PROMINENT_KEYS.has(key))
  const regularDetails = detailEntries.filter(([key]) => !PROMINENT_KEYS.has(key))

  return (
    <div className="py-3 border-b border-slate-100 last:border-b-0">
      <div className="flex items-baseline gap-3">
        {onLemmaClick ? (
          <button
            type="button"
            onClick={() => onLemmaClick(parse.lemma)}
            className="text-base font-medium underline hover:opacity-80 underline-offset-2 cursor-pointer"
          >
            <GreekText>{parse.lemma}</GreekText>
          </button>
        ) : (
          <GreekText className="text-base font-medium">{parse.lemma}</GreekText>
        )}
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${getPosColor(parse.part_of_speech)}`}>
          {parse.part_of_speech}
        </span>
        {parse.parse_pct != null && (
          <span className="rounded-full px-2 py-0.5 text-[10px] font-medium bg-slate-100 text-slate-600">
            {parse.parse_pct.toFixed(1)}%
          </span>
        )}
        {parse.transliteration && (
          <span className="text-xs text-slate-500 italic">{parse.transliteration}</span>
        )}
      </div>

      {prominentDetails.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {prominentDetails.map(([key, value]) => (
            <span
              key={key}
              className="rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-800"
            >
              <span className="font-bold text-indigo-500">{DETAIL_LABELS[key] ?? key}:</span>{' '}
              {value}
            </span>
          ))}
        </div>
      )}

      {parse.analysis_label && (
        <div className="mt-1 text-xs text-slate-500">{parse.analysis_label}</div>
      )}

      {regularDetails.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-1.5">
          {regularDetails.map(([key, value]) => (
            <span
              key={key}
              className="rounded bg-slate-50 px-2 py-0.5 text-xs text-slate-600"
            >
              <span className="font-medium text-slate-400">{DETAIL_LABELS[key] ?? key}:</span>{' '}
              {value}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
