import { useEffect } from 'react'
import { useAppStore } from './stores/appStore'
import { Sidebar } from './components/shared/Sidebar'
import { HighlightPopup } from './components/shared/HighlightPopup'
import { DictionarySearch } from './components/dictionary/DictionarySearch'
import { TextCatalog } from './components/texts/TextCatalog'
import { TextReader } from './components/texts/TextReader'
import { WorkbenchPanel } from './components/workbench/WorkbenchPanel'
import { AboutPage } from './components/about/AboutPage'

// ── Pages ─────────────────────────────────────────────────────────────

function DictionaryPage() {
  return <DictionarySearch />
}

function TextsPage() {
  const selectedTextId = useAppStore((s) => s.selectedTextId)

  if (selectedTextId) {
    return <TextReader />
  }

  return <TextCatalog />
}

function WorkbenchPage() {
  return <WorkbenchPanel />
}

function AboutTabPage() {
  return <AboutPage />
}

// ── Tab content map ───────────────────────────────────────────────────

const pages = {
  dictionary: DictionaryPage,
  texts: TextsPage,
  workbench: WorkbenchPage,
  about: AboutTabPage,
} as const

// ── App ───────────────────────────────────────────────────────────────

function App() {
  const activeTab = useAppStore((s) => s.activeTab)
  const setActiveTab = useAppStore((s) => s.setActiveTab)
  const darkMode = useAppStore((s) => s.darkMode)
  const toggleDarkMode = useAppStore((s) => s.toggleDarkMode)
  const Page = pages[activeTab]

  // Keyboard shortcuts: Ctrl+K -> Dictionary, Ctrl+J -> Texts, Ctrl+/ -> Workbench
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.ctrlKey || e.metaKey) {
        if (e.key === 'k') {
          e.preventDefault()
          setActiveTab('dictionary')
          requestAnimationFrame(() => {
            const input = document.querySelector<HTMLInputElement>(
              'input[placeholder*="Search Greek"], input[placeholder*="Search"]'
            )
            input?.focus()
          })
        } else if (e.key === 'j') {
          e.preventDefault()
          setActiveTab('texts')
        } else if (e.key === '/') {
          e.preventDefault()
          setActiveTab('workbench')
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [setActiveTab])

  return (
    <div className={darkMode ? 'dark' : ''}>
      <div className="flex h-screen bg-white text-slate-800 font-sans dark:bg-slate-950 dark:text-slate-100">
        <Sidebar />
        <main className="flex-1 overflow-y-auto relative">
          <button
            type="button"
            onClick={toggleDarkMode}
            className="absolute top-4 right-6 h-8 w-8 rounded-full border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 cursor-pointer hover:border-red-800 hover:text-red-800 dark:hover:border-red-300 dark:hover:text-red-300"
            aria-label={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
            title={darkMode ? 'Light mode' : 'Dark mode'}
          >
            {darkMode ? '☀' : '☾'}
          </button>
          <div className="max-w-6xl mx-auto px-8 py-10">
            <Page />
          </div>
        </main>
        <HighlightPopup />
      </div>
    </div>
  )
}

export default App
