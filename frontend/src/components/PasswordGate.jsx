import { useState } from 'react'
import { getSettings, setAppPassword } from '../api'

export default function PasswordGate({ onUnlock }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setAppPassword(password)
    try {
      await getSettings()
      onUnlock()
    } catch {
      setAppPassword('')
      setError('Incorrect password')
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 dark:bg-black/70 flex items-center justify-center p-4 z-50">
      <form
        onSubmit={handleSubmit}
        className="bg-white dark:bg-gray-800 rounded-xl shadow-xl max-w-sm w-full p-6 space-y-4"
      >
        <h1 className="text-lg font-bold">Password required</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          This instance is protected. Enter the app password to continue.
        </p>
        <input
          type="password"
          autoFocus
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full border rounded-md p-2 text-sm dark:bg-gray-900 dark:border-gray-600"
          placeholder="App password"
        />
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <button
          type="submit"
          disabled={busy || !password}
          className="w-full bg-indigo-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
        >
          {busy ? 'Checking…' : 'Unlock'}
        </button>
      </form>
    </div>
  )
}
