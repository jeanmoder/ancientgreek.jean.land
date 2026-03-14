import { useCallback, useEffect, useRef, useState } from 'react'
import type { DictionaryEntry, FullLookupResult, MorphologyResult } from '../api/client'
import { fullLookup } from '../api/client'

interface DictionaryState {
  query: string
  morphology: MorphologyResult | null
  definitions: DictionaryEntry[]
  liveDefinitions: DictionaryEntry[]
  transliteration: string
  paradigms: FullLookupResult['paradigms']
  paradigm: FullLookupResult['paradigm']
  citationForm: string
  loading: boolean
  liveLoading: boolean
  error: string | null
  liveError: string | null
}

interface SearchOptions {
  liveEntry?: boolean
}

export function useDictionary(initialQuery: string | null) {
  const [state, setState] = useState<DictionaryState>({
    query: initialQuery ?? '',
    morphology: null,
    definitions: [],
    liveDefinitions: [],
    transliteration: '',
    paradigms: [],
    paradigm: null,
    citationForm: '',
    loading: false,
    liveLoading: false,
    error: null,
    liveError: null,
  })

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const search = useCallback(async (word: string, options: SearchOptions = {}) => {
    const trimmed = word.trim()
    if (!trimmed) {
      setState((prev) => ({
        ...prev,
        morphology: null,
        definitions: [],
        liveDefinitions: [],
        transliteration: '',
        paradigms: [],
        paradigm: null,
        citationForm: '',
        loading: false,
        liveLoading: false,
        error: null,
        liveError: null,
      }))
      return
    }

    if (abortRef.current) {
      abortRef.current.abort()
    }
    abortRef.current = new AbortController()

    setState((prev) => ({
      ...prev,
      loading: true,
      error: null,
      liveLoading: false,
      liveError: null,
      liveDefinitions: [],
    }))

    try {
      const result = await fullLookup(trimmed, {}, { liveEntry: options.liveEntry === true })
      setState((prev) => ({
        ...prev,
        morphology: { word: result.word, parses: result.parses },
        definitions: result.definitions,
        liveDefinitions: [],
        transliteration: result.transliteration,
        paradigms: result.paradigms ?? (result.paradigm ? [result.paradigm] : []),
        paradigm: result.paradigm,
        citationForm: result.citation_form || '',
        loading: false,
        error: null,
        liveLoading: false,
        liveError: null,
      }))
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      setState((prev) => ({
        ...prev,
        morphology: null,
        definitions: [],
        liveDefinitions: [],
        transliteration: '',
        paradigms: [],
        paradigm: null,
        citationForm: '',
        loading: false,
        liveLoading: false,
        error: err instanceof Error ? err.message : 'Search failed',
      }))
    }
  }, [])

  const setQuery = useCallback(
    (newQuery: string) => {
      setState((prev) => ({ ...prev, query: newQuery }))

      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
      }
      debounceRef.current = setTimeout(() => {
        void search(newQuery)
      }, 300)
    },
    [search],
  )

  const openEntry = useCallback(
    async (word: string) => {
      setState((prev) => ({ ...prev, query: word }))
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
      }
      await search(word)
      setState((prev) => ({ ...prev, liveLoading: true, liveError: null, liveDefinitions: [] }))
      try {
        const live = await fullLookup(word, {}, { liveEntry: true })
        setState((prev) => ({
          ...prev,
          liveDefinitions: live.definitions,
          liveLoading: false,
          liveError: null,
        }))
      } catch (err) {
        setState((prev) => ({
          ...prev,
          liveLoading: false,
          liveError: err instanceof Error ? err.message : 'Live dictionary lookup failed',
        }))
      }
    },
    [search],
  )

  // Trigger search on mount if there's an initial query
  useEffect(() => {
    if (initialQuery) {
      void search(initialQuery)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Sync when external query changes (e.g. from highlight popup)
  useEffect(() => {
    if (initialQuery && initialQuery !== state.query) {
      setState((prev) => ({ ...prev, query: initialQuery }))
      void search(initialQuery)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuery])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
      }
      if (abortRef.current) {
        abortRef.current.abort()
      }
    }
  }, [])

  return {
    query: state.query,
    morphology: state.morphology,
    definitions: state.definitions,
    transliteration: state.transliteration,
    paradigms: state.paradigms,
    paradigm: state.paradigm,
    citationForm: state.citationForm,
    loading: state.loading,
    liveLoading: state.liveLoading,
    error: state.error,
    liveError: state.liveError,
    liveDefinitions: state.liveDefinitions,
    setQuery,
    search,
    openEntry,
  }
}
