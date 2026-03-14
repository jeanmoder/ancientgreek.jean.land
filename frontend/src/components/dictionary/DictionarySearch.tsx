import { useAppStore } from '../../stores/appStore'
import { useDictionary } from '../../hooks/useDictionary'
import { MorphologyCard } from './MorphologyCard'
import { DictionaryEntryCard } from './DictionaryEntryCard'
import { LogeionTabs } from './LogeionTabs'
import { GreekText } from '../shared/GreekText'

export function DictionarySearch() {
  const dictionaryQuery = useAppStore((s) => s.dictionaryQuery)
  const {
    query,
    morphology,
    definitions,
    transliteration,
    paradigms,
    citationForm,
    loading,
    liveLoading,
    error,
    liveError,
    liveDefinitions,
    setQuery,
    search,
    openEntry,
  } =
    useDictionary(dictionaryQuery)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    void search(query)
  }

  const handleWordDrilldown = (word: string) => {
    openEntry(word)
  }

  return (
    <div>
      {/* Search */}
      <form onSubmit={handleSubmit}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search Greek or English..."
          className="w-full text-lg py-3 border-b border-slate-300 dark:border-slate-700 bg-transparent text-slate-800 dark:text-slate-100 placeholder:text-slate-500 dark:placeholder:text-slate-400 focus:outline-none focus:border-slate-500 transition-colors"
        />
      </form>

      {/* Loading */}
      {loading && (
        <div className="mt-8 text-sm text-slate-500">
          <span className="inline-block h-3 w-3 animate-spin rounded-full border border-slate-300 border-t-slate-500 mr-2" />
          Searching...
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mt-8 text-sm text-red-500">
          {error}
          <span
            onClick={() => void search(query)}
            className="ml-3 text-slate-500 hover:text-red-800 dark:hover:text-red-300 cursor-pointer"
          >
            Retry
          </span>
        </div>
      )}

      {/* Results */}
      {!loading && !error && (morphology?.parses.length || definitions.length > 0) && (
        <div className="mt-8">
          {/* Citation form header */}
          {citationForm && (
            <div className="mb-8">
              <GreekText className="!text-2xl font-medium text-slate-900">{citationForm}</GreekText>
              {transliteration && (
                <p className="text-sm text-slate-500 italic mt-1">{transliteration}</p>
              )}
            </div>
          )}
          {!citationForm && transliteration && (
            <div className="mb-8">
              <p className="text-sm text-slate-500 italic">{transliteration}</p>
            </div>
          )}

          {/* Morphology */}
          {(definitions.length > 0 || liveLoading || !!liveError || liveDefinitions.length > 0) && (
            <section className="mb-10">
              <h2 className="text-xs font-medium tracking-wide text-red-800 dark:text-red-300 mb-3">
                Definitions
              </h2>
              {definitions.length > 0 && (
                <div>
                  {definitions.map((entry, i) => (
                    <DictionaryEntryCard
                      key={i}
                      entry={entry}
                      onWordClick={handleWordDrilldown}
                    />
                  ))}
                </div>
              )}
              {liveLoading && (
                <p className="mt-4 text-sm text-slate-500">Loading live Logeion dictionaries...</p>
              )}
              {liveError && (
                <p className="mt-4 text-sm text-red-500">{liveError}</p>
              )}
              {liveDefinitions[0] && <LogeionTabs entry={liveDefinitions[0]} />}
            </section>
          )}

          {/* Morphology */}
          {morphology && morphology.parses.length > 0 && (
            <section className="mb-10">
              <h2 className="text-xs font-medium tracking-wide text-red-800 dark:text-red-300 mb-3">
                Morphology
              </h2>
              <div>
                {morphology.parses.map((parse, i) => (
                  <MorphologyCard key={i} parse={parse} onLemmaClick={handleWordDrilldown} />
                ))}
              </div>
            </section>
          )}

          {/* Paradigm tables */}
          {paradigms.length > 0 && (
            <section className="mb-10 space-y-8">
              {paradigms.map((table, tableIdx) => (
                <div key={tableIdx}>
                  <div className="mb-3">
                    <h2 className="text-xs font-medium tracking-wide text-red-800 dark:text-red-300">
                      {table.title}
                    </h2>
                    {table.source_url && (
                      <a
                        href={table.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[11px] text-slate-600 dark:text-slate-300 hover:text-red-800 dark:hover:text-red-300"
                      >
                        Wiktionary source
                      </a>
                    )}
                  </div>
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-200">
                        {table.headers.map((h, i) => (
                          <th key={i} className="text-left py-2 pr-4 text-xs font-medium text-slate-500">
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
                              className={`py-2 pr-4 ${j === 0 ? 'text-xs text-slate-500' : 'text-slate-700 font-greek'}`}
                            >
                              {cell}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {table.note && (
                    <p className="mt-2 text-[11px] text-slate-500 dark:text-slate-400 italic">
                      Note: {table.note}
                    </p>
                  )}
                </div>
              ))}
            </section>
          )}
        </div>
      )}

      {/* Empty state */}
      {!loading &&
        !error &&
        query.trim().length > 0 &&
        morphology !== null &&
        morphology.parses.length === 0 &&
        definitions.length === 0 && (
          <div className="mt-8 text-sm text-slate-500">
            No results found for &ldquo;{query}&rdquo;
          </div>
        )}
    </div>
  )
}
