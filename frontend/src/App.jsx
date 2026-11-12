import { Link, NavLink, Route, Routes } from 'react-router-dom'
import HomePage from './pages/HomePage'
import ReviewPage from './pages/ReviewPage'
import SettingsPage from './pages/SettingsPage'
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
              className="ml-1 px-2.5 py-1.5 rounded-md text-lg hover:bg-gray-100 dark:hover:bg-gray-700"
            >
              {dark ? '☀️' : '🌙'}
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
    </div>
  )
}
