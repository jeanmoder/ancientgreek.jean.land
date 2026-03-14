import { useAppStore } from '../../stores/appStore'
import type { TabId } from '../../stores/appStore'

interface TabDef {
  id: TabId
  label: string
  shortcut?: string
}

const tabs: TabDef[] = [
  { id: 'dictionary', label: 'Dictionary', shortcut: '\u2318K' },
  { id: 'texts', label: 'Texts', shortcut: '\u2318J' },
  { id: 'workbench', label: 'Textbox', shortcut: '\u2318/' },
]

export function Sidebar() {
  const activeTab = useAppStore((s) => s.activeTab)
  const setActiveTab = useAppStore((s) => s.setActiveTab)
  const syntaxLegendVisible = useAppStore((s) => s.syntaxLegendVisible)

  return (
    <aside className="flex flex-col h-screen w-56 shrink-0 border-r border-slate-100 dark:border-slate-800">
      {/* Header */}
      <div className="px-3 pt-5 pb-4">
        <span className="inline-flex items-center px-3 py-1 text-[13px] leading-none tracking-[0.01em] text-red-800 dark:text-red-300 brand-rounded lowercase">
          ancientgreek.jean.land
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 flex flex-col px-3">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id
          return (
            <div
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`
                flex items-center justify-between px-3 py-2 cursor-pointer
                text-sm transition-colors duration-100
                ${isActive
                  ? 'text-slate-900 dark:text-slate-100 font-medium'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
                }
              `}
            >
              <span>{tab.label}</span>
              {tab.shortcut && (
                <span className="text-[10px] text-slate-300 font-mono">{tab.shortcut}</span>
              )}
            </div>
          )
        })}
      </nav>

      {syntaxLegendVisible && (
        <div className="px-5 pb-5 text-xs space-y-1">
          <p className="text-red-800 dark:text-red-300">Syntax</p>
          <p className="text-red-600">Subject</p>
          <p className="text-green-600">Verb</p>
          <p className="text-blue-600">Object</p>
          <p className="text-cyan-700">Complement</p>
          <p className="text-violet-700">Prep Complement</p>
          <p className="text-fuchsia-700">Apposition</p>
          <p className="text-purple-600">Modifier</p>
          <p className="text-emerald-700">Article</p>
          <p className="text-amber-600">Particle / Conj / Prep</p>
          <p className="text-slate-600 dark:text-slate-300">Other</p>
        </div>
      )}

      <div className="px-5 pb-4 mt-auto text-[11px] leading-snug text-slate-500 dark:text-slate-300 font-sans space-y-1">
        <div>
          <button
            type="button"
            onClick={() => setActiveTab('about')}
            className="cursor-pointer hover:text-red-800 dark:hover:text-red-300"
          >
            about
          </button>
        </div>
        <div>
          made with <span className="text-red-800 dark:text-red-300">♥</span> by{' '}
          <a
            className="hover:text-red-800 dark:hover:text-red-300"
            href="https://jean.land"
            target="_blank"
            rel="noreferrer"
          >
            jean
          </a>
        </div>
      </div>
    </aside>
  )
}
