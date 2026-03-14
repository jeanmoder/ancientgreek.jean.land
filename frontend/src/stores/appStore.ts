import { create } from 'zustand'

export type TabId = 'dictionary' | 'texts' | 'workbench' | 'about'

interface AppState {
  activeTab: TabId
  setActiveTab: (tab: TabId) => void

  selectedTextId: string | null
  setSelectedTextId: (id: string | null) => void

  selectedBook: number
  setSelectedBook: (book: number) => void

  dictionaryQuery: string | null
  setDictionaryQuery: (query: string | null) => void

  darkMode: boolean
  toggleDarkMode: () => void

  syntaxLegendVisible: boolean
  setSyntaxLegendVisible: (visible: boolean) => void
}

export const useAppStore = create<AppState>((set) => ({
  activeTab: 'dictionary',
  setActiveTab: (tab) => set({ activeTab: tab }),

  selectedTextId: null,
  setSelectedTextId: (id) => set({ selectedTextId: id }),

  selectedBook: 1,
  setSelectedBook: (book) => set({ selectedBook: book }),

  dictionaryQuery: null,
  setDictionaryQuery: (query) => set({ dictionaryQuery: query }),

  darkMode: false,
  toggleDarkMode: () => set((state) => ({ darkMode: !state.darkMode })),

  syntaxLegendVisible: false,
  setSyntaxLegendVisible: (visible) => set({ syntaxLegendVisible: visible }),
}))
