import { useState } from 'react'
import { analyzeSyntax } from '../../api/client'
import type { SyntaxWord } from '../../api/client'
import { GreekText } from '../shared/GreekText'

const ALLOWED_CHARS_RE = /[\u0370-\u03FF\u1F00-\u1FFF\u0300-\u036F·;;,\.\?!\s]/u

function filterAncientGreek(text: string): string {
  return Array.from(text)
    .filter((ch) => ALLOWED_CHARS_RE.test(ch))
    .join('')
}

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

function splitIntoSentences(text: string): string[] {
  const parts = (text.match(/[^.!?;·;]+[.!?;·;]*/gu) ?? [text])
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
  return parts.length > 0 ? parts : [text.trim()]
}

function fallbackSyntaxWords(text: string): SyntaxWord[] {
  const words = text.match(/[\u0370-\u03FF\u1F00-\u1FFF]+/gu) ?? []
  return words.map((word) => ({ word, role: 'other' }))
}

export function WorkbenchPanel() {
  const [input, setInput] = useState('')
  const [syntaxWords, setSyntaxWords] = useState<SyntaxWord[] | null>(null)
  const [syntaxLoading, setSyntaxLoading] = useState(false)

  const hasInput = input.trim().length > 0

  const updateInput = (value: string) => {
    setInput(value)
    setSyntaxWords(null)
  }

  const renderSyntaxText = (text: string, words: SyntaxWord[]) => {
    const segments = text.split(/([\u0370-\u03FF\u1F00-\u1FFF]+)/gu)
    let wordIdx = 0
    return segments.map((segment, idx) => {
      if (!segment) return null
      const isGreekWord = /^[\u0370-\u03FF\u1F00-\u1FFF]+$/u.test(segment)
      if (!isGreekWord) return <span key={idx}>{segment}</span>
      const role = words[wordIdx]?.role ?? 'other'
      wordIdx += 1
      return (
        <span key={idx} className={ROLE_STYLES[role] || ROLE_STYLES.other} title={role}>
          {segment}
        </span>
      )
    })
  }

  const handleWholeSyntax = () => {
    if (!hasInput) return
    if (syntaxWords) {
      setSyntaxWords(null)
      return
    }
    const text = input.trim()
    const sentences = splitIntoSentences(text)
    setSyntaxLoading(true)
    Promise.all(sentences.map((sentence) => analyzeSyntax(sentence)))
      .then((sentenceResults) => {
        setSyntaxWords(sentenceResults.flat())
      })
      .catch(() => {
        setSyntaxWords(fallbackSyntaxWords(text))
      })
      .finally(() => {
        setSyntaxLoading(false)
      })
  }

  return (
    <div className="max-w-6xl">
      <div data-reader-panel className="xl:pr-[360px]">
        <h1 className="text-2xl font-semibold mb-2">Textbox</h1>
        <p className="text-sm text-red-800 dark:text-red-300 mb-4">
          Enter Ancient Greek text. Pasted content is automatically stripped to Ancient Greek characters.
        </p>
        <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
          You may then parse, translate, and analyze the text you provide here via highlighting as you would elsewhere on the website.
        </p>

        <textarea
          value={input}
          onChange={(e) => updateInput(e.target.value)}
          onPaste={(e) => {
            e.preventDefault()
            const pasted = e.clipboardData.getData('text')
            const cleaned = filterAncientGreek(pasted)
            const target = e.currentTarget
            const start = target.selectionStart ?? input.length
            const end = target.selectionEnd ?? input.length
            const next = input.slice(0, start) + cleaned + input.slice(end)
            updateInput(next)
          }}
          placeholder="Paste Ancient Greek text here..."
          className="w-full min-h-40 border border-slate-300 px-3 py-2 text-base text-slate-800 dark:text-slate-100 placeholder:text-slate-500 dark:placeholder:text-slate-400 focus:outline-none focus:border-slate-500 dark:bg-slate-950 dark:border-slate-700"
        />

        {hasInput && (
          <div className="mt-4 mb-2">
            <button
              type="button"
              onClick={handleWholeSyntax}
              disabled={syntaxLoading}
              className="text-sm text-slate-600 dark:text-slate-300 hover:text-red-800 dark:hover:text-red-300 disabled:text-slate-400 cursor-pointer"
            >
              {syntaxLoading ? 'Parsing syntax…' : syntaxWords ? 'Hide syntax' : 'Parse syntax'}
            </button>
          </div>
        )}

        <div className="mt-4 border border-slate-200 dark:border-slate-700 px-3 py-2 min-h-20">
          <GreekText className="block whitespace-pre-wrap">
            {input.trim() ? (syntaxWords ? renderSyntaxText(input, syntaxWords) : input) : '— Greek preview —'}
          </GreekText>
        </div>
      </div>
    </div>
  )
}
