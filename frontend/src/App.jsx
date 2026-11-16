import { useEffect, useState } from 'react'
import { Link, NavLink, Route, Routes } from 'react-router-dom'
import HomePage from './pages/HomePage'
import ReviewPage from './pages/ReviewPage'
import SettingsPage from './pages/SettingsPage'
import PasswordGate from './components/PasswordGate'
import { initTheme, toggleTheme, useDarkMode } from './theme'

initTheme()

const navClass = ({ isActive }) =>
  `px-3 py-1.5 rounded-md text-sm font-medium ${
    isActive
      ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-200'
      : 'text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white'
  }`

export default function App() {
  const dark = useDarkMode()
  const [locked, setLocked] = useState(false)

  useEffect(() => {
    const handle = () => setLocked(true)
    window.addEventListener('auth-required', handle)
    return () => window.removeEventListener('auth-required', handle)
  }, [])

  return (
    <div className="min-h-screen">
      <header className="bg-white border-b dark:bg-gray-800 dark:border-gray-700">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 font-bold text-lg hover:opacity-80">
            <img src="/favicon.svg" alt="" className="h-6 w-6 rounded-md" />
            Resumaxxing
          </Link>
          <nav className="flex gap-2 items-center">
            <NavLink to="/" end className={navClass}>Reviews</NavLink>
            <NavLink to="/settings" className={navClass}>Settings</NavLink>
            <button
              onClick={toggleTheme}
              title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
              aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
              className="ml-1 p-1.5 rounded-md text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-700 dark:hover:text-white"
            >
              {dark ? (
                <svg
                  className="h-5 w-5"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  aria-hidden="true"
                >
                  <circle cx="12" cy="12" r="4" />
                  <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
                </svg>
              ) : (
                <svg
                  className="h-5 w-5"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
              )}
            </button>
          </nav>
        </div>
      </header>
      <main className="max-w-5xl mx-auto px-4 py-8">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/reviews/:id" element={<ReviewPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
      {locked && (
        <PasswordGate onUnlock={() => { setLocked(false); window.location.reload() }} />
      )}
    </div>
  )
}
