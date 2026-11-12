import { useEffect, useState } from 'react'
import { getSettings, saveSettings } from '../api'

const PROVIDERS = ['mock', 'claude', 'ollama', 'opencode']

const KEY_FIELDS = {
  claude: { field: 'claude_key', label: 'Claude API Key', placeholder: 'sk-ant-…' },
  ollama: { field: 'ollama_key', label: 'Ollama Cloud API Key', placeholder: '' },
  opencode: { field: 'opencode_key', label: 'Opencode Cloud API Key', placeholder: '' },
}

export default function SettingsPage() {
  const [form, setForm] = useState({
    llm_provider: 'mock',
    claude_key: '',
    ollama_key: '',
    opencode_key: '',
    linkedin_url: '',
  })
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    getSettings().then((s) =>
      setForm((f) => ({
        ...f,
        llm_provider: s.llm_provider ?? 'mock',
        linkedin_url: s.linkedin_url ?? '',
        // API keys are stored server-side; fields stay blank unless changed
      })),
    ).catch((e) => setError(e.message))
  }, [])

  function set(field) {
    return (e) => { setForm((f) => ({ ...f, [field]: e.target.value })); setSaved(false) }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    try {
      await saveSettings(form)
      setSaved(true)
    } catch (e2) {
      setError(e2.message)
    }
  }

  return (
    <div className="max-w-xl">
      <h1 className="text-2xl font-bold mb-6">Settings</h1>
      <form onSubmit={handleSubmit} className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-5 space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">LLM Provider</label>
          <select value={form.llm_provider} onChange={set('llm_provider')}
            className="w-full border rounded-md p-2 text-sm dark:bg-gray-900 dark:border-gray-600">
            {PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
            "mock" uses a local keyword heuristic — no API key required.
          </p>
        </div>
        {KEY_FIELDS[form.llm_provider] && (
          <div>
            <label className="block text-sm font-medium mb-1">
              {KEY_FIELDS[form.llm_provider].label}
            </label>
            <input
              type="password"
              value={form[KEY_FIELDS[form.llm_provider].field]}
              onChange={set(KEY_FIELDS[form.llm_provider].field)}
              placeholder={KEY_FIELDS[form.llm_provider].placeholder}
              className="w-full border rounded-md p-2 text-sm dark:bg-gray-900 dark:border-gray-600"
            />
          </div>
        )}
        <div>
          <label className="block text-sm font-medium mb-1">LinkedIn Profile URL (optional)</label>
          <input type="url" value={form.linkedin_url} onChange={set('linkedin_url')}
            placeholder="https://linkedin.com/in/…" className="w-full border rounded-md p-2 text-sm dark:bg-gray-900 dark:border-gray-600" />
        </div>
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <button type="submit"
          className="bg-indigo-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-indigo-700">
          Save Settings
        </button>
        {saved && <span className="ml-3 text-sm text-green-600">Saved.</span>}
      </form>
    </div>
  )
}
