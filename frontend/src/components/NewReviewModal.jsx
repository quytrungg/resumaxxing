import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createReview, getSettings, listProviderModels, uploadCv } from '../api'
import ModelSelect from './ModelSelect'
import {
  PROVIDERS as LLM_PROVIDERS,
  PROVIDER_MAP,
  isProviderConfigured,
  loadCatalog,
  rememberModels,
} from '../llmProviders'

const PROVIDERS = [
  { value: 'mock', label: 'Mock (local heuristic)' },
  ...LLM_PROVIDERS.map((p) => ({ value: p.value, label: p.label })),
]

export default function NewReviewModal({ onClose }) {
  const navigate = useNavigate()
  const [cvFile, setCvFile] = useState(null)
  const [mode, setMode] = useState('text')
  const [jdText, setJdText] = useState('')
  const [jdUrl, setJdUrl] = useState('')
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [savedProvider, setSavedProvider] = useState('mock')
  const [savedSettings, setSavedSettings] = useState(null)
  const [models, setModels] = useState([])
  const [modelsLoading, setModelsLoading] = useState(false)
  const [modelError, setModelError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    getSettings()
      .then((s) => {
        setSavedProvider(s.llm_provider ?? 'mock')
        setSavedSettings(s)
      })
      .catch(() => {})
  }, [])

  const effectiveProvider = provider || savedProvider
  const usesModelName = effectiveProvider !== 'mock'
  const effectiveSpec = PROVIDER_MAP[effectiveProvider]
  const providerDefault = (effectiveSpec
    && (savedSettings?.[effectiveSpec.modelField] || effectiveSpec.defaultModel)) || null

  useEffect(() => {
    if (!usesModelName) {
      setModels([])
      setModelError(null)
      setModelsLoading(false)
      return undefined
    }
    const cached = loadCatalog()[effectiveProvider]
    setModels(cached || [])
    setModelError(null)
    setModelsLoading(true)
    let cancelled = false
    listProviderModels({ provider: effectiveProvider })
      .then((r) => {
        if (cancelled) return
        setModels(r.models)
        rememberModels(loadCatalog(), effectiveProvider, r.models)
      })
      .catch((e2) => {
        if (!cancelled) setModelError(e2.message)
      })
      .finally(() => {
        if (!cancelled) setModelsLoading(false)
      })
    return () => { cancelled = true }
  }, [effectiveProvider, usesModelName])

  async function handleSubmit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (cvFile) await uploadCv(cvFile)
      const payload = mode === 'url' ? { jd_url: jdUrl } : { jd_text: jdText }
      payload.llm_provider = effectiveProvider
      if (usesModelName && model.trim()) payload.llm_model = model.trim()
      const review = await createReview(payload)
      navigate(`/reviews/${review.id}`)
    } catch (e2) {
      setError(e2.message)
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/40 dark:bg-black/60 flex items-center justify-center p-4 z-50"
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-gray-800 rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-bold">New CV Review</h1>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 text-2xl leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-6">
          <section className="border dark:border-gray-700 rounded-lg p-4">
            <h2 className="font-semibold mb-2">1. Base CV</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
              Upload a new CV (PDF, DOCX or TXT). If you skip this, your most recent upload is used.
            </p>
            <input
              type="file"
              accept=".pdf,.docx,.txt"
              onChange={(e) => setCvFile(e.target.files?.[0] ?? null)}
              className="text-sm"
            />
          </section>

          <section className="border dark:border-gray-700 rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
              <h2 className="font-semibold">2. Job Description</h2>
              <div className="flex gap-2 text-sm">
                <button type="button" onClick={() => setMode('text')}
                  className={mode === 'text' ? 'font-semibold text-indigo-600 dark:text-indigo-400' : 'text-gray-500 dark:text-gray-400'}>
                  Paste text
                </button>
                <span className="text-gray-300 dark:text-gray-600">|</span>
                <button type="button" onClick={() => setMode('url')}
                  className={mode === 'url' ? 'font-semibold text-indigo-600 dark:text-indigo-400' : 'text-gray-500 dark:text-gray-400'}>
                  URL
                </button>
              </div>
            </div>
            {mode === 'text' ? (
              <textarea
                className="w-full border dark:border-gray-600 dark:bg-gray-900 rounded-md p-3 h-48 text-sm"
                placeholder="Paste the full job description…"
                value={jdText}
                onChange={(e) => setJdText(e.target.value)}
              />
            ) : (
              <input
                className="w-full border dark:border-gray-600 dark:bg-gray-900 rounded-md p-3 text-sm"
                placeholder="https://jobs.example.com/posting/123"
                value={jdUrl}
                onChange={(e) => setJdUrl(e.target.value)}
              />
            )}
          </section>

          <section className="border dark:border-gray-700 rounded-lg p-4">
            <h2 className="font-semibold mb-2">3. Review model</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
              Choose which LLM reviews this CV. The choice is pinned to this review —
              later rescoring, finalize and the cover letter use it too.
            </p>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium mb-1">Provider</label>
                <select
                  value={effectiveProvider}
                  onChange={(e) => { setProvider(e.target.value); setModel('') }}
                  className="w-full border rounded-md p-2 text-sm dark:bg-gray-900 dark:border-gray-600"
                >
                  {PROVIDERS.map((p) => {
                    const providerSpec = PROVIDER_MAP[p.value]
                    const mask = providerSpec ? savedSettings?.[providerSpec.keyField] : ''
                    const subscribed = p.value === 'claude'
                      && Boolean(savedSettings?.claude_oauth_connected)
                    const configured = p.value === 'mock'
                      || isProviderConfigured(savedSettings, providerSpec)
                      || savedProvider === p.value
                    const suffix = mask || (subscribed ? 'subscription' : '')
                    return (
                      <option key={p.value} value={p.value} disabled={!configured}>
                        {suffix
                          ? `${p.label} · ${suffix}`
                          : `${p.label}${configured ? '' : ' — no key saved'}`}
                      </option>
                    )
                  })}
                </select>
              </div>
              {usesModelName && (
                <div>
                  <label className="block text-sm font-medium mb-1">Model (optional)</label>
                  <ModelSelect
                    value={model}
                    onChange={setModel}
                    options={models}
                    providerLabel={effectiveSpec?.label || effectiveProvider}
                    defaultOption={providerDefault}
                    placeholder={providerDefault || 'Provider default'}
                    loading={modelsLoading}
                    error={modelError}
                  />
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                    Fetched from the selected provider. Leave empty for its default.
                  </p>
                </div>
              )}
            </div>
          </section>

          {error && <p className="text-red-600 text-sm">{error}</p>}
          <button
            type="submit"
            disabled={busy || (mode === 'text' ? !jdText.trim() : !jdUrl.trim())}
            className="bg-indigo-600 text-white px-5 py-2.5 rounded-md font-medium hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? 'Analyzing…' : 'Analyze CV against JD'}
          </button>
        </form>
      </div>
    </div>
  )
}
