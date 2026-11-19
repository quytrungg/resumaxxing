import { useEffect, useState } from 'react'
import {
  deleteProvider,
  disconnectClaudeOAuth,
  exchangeClaudeOAuth,
  getSettings,
  listProviderModels,
  saveSettings,
  startClaudeOAuth,
} from '../api'
import ModelSelect from '../components/ModelSelect'
import {
  PROVIDERS,
  PROVIDER_MAP,
  forgetModels,
  isProviderConfigured,
  loadCatalog,
  rememberModels,
} from '../llmProviders'

function firstProvider(settings) {
  const active = settings?.llm_provider
  if (PROVIDER_MAP[active]) return active
  return PROVIDERS.find((p) => !isProviderConfigured(settings, p))?.value || 'claude'
}

const chipIcon = (
  <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className="h-5 w-5 text-indigo-500">
    <rect x="6" y="6" width="12" height="12" rx="2.5" stroke="currentColor" strokeWidth="1.6" />
    <rect x="9.5" y="9.5" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.4" />
    <path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3"
      stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
  </svg>
)

const trashIcon = (
  <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className="h-4 w-4">
    <path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a1.5 1.5 0 001.5 1.4h7a1.5 1.5 0 001.5-1.4L17 7M9 7V5.5A1.5 1.5 0 0110.5 4h3A1.5 1.5 0 0115 5.5V7"
      stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

export default function SettingsPage() {
  const [settings, setSettings] = useState(null)
  const [catalog, setCatalog] = useState(loadCatalog)
  const [form, setForm] = useState({
    provider: 'claude', api_key: '', base_url: '', model: '',
  })
  const [linkedin, setLinkedin] = useState('')
  const [saving, setSaving] = useState(false)
  const [savingLinkedin, setSavingLinkedin] = useState(false)
  const [testing, setTesting] = useState(null)
  const [activating, setActivating] = useState(null)
  const [testResults, setTestResults] = useState({})
  const [modelsLoading, setModelsLoading] = useState(false)
  const [modelError, setModelError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [oauthFlow, setOauthFlow] = useState(null)
  const [oauthCode, setOauthCode] = useState('')
  const [oauthBusy, setOauthBusy] = useState(false)
  const [oauthError, setOauthError] = useState(null)
  const [oauthNotice, setOauthNotice] = useState(null)

  const spec = PROVIDER_MAP[form.provider]
  const models = catalog[form.provider] || []
  const claudeConnected = Boolean(settings?.claude_oauth_connected)

  function fillForm(provider, nextSettings = settings) {
    const nextSpec = PROVIDER_MAP[provider]
    setForm({
      provider,
      api_key: '',
      base_url: nextSettings?.[nextSpec.baseUrlField] || '',
      model: nextSettings?.[nextSpec.modelField] || '',
    })
    setModelError(null)
  }

  useEffect(() => {
    getSettings()
      .then((s) => {
        setSettings(s)
        setLinkedin(s.linkedin_url || '')
        fillForm(firstProvider(s), s)
        // Warm the model catalog for every configured provider so the New
        // Review modal has options immediately.
        for (const p of PROVIDERS) {
          if (!isProviderConfigured(s, p)) continue
          listProviderModels({ provider: p.value })
            .then((r) => setCatalog((c) => rememberModels(c, p.value, r.models)))
            .catch(() => {})
        }
      })
      .catch((e) => setNotice({ type: 'error', text: e.message }))
  }, [])

  useEffect(() => {
    if (!settings) return undefined
    const current = PROVIDER_MAP[form.provider]
    const typedKey = form.api_key.trim()
    const localOllama = current.value === 'ollama'
      && /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?/.test(form.base_url.trim())
    const canFetch = typedKey || isProviderConfigured(settings, current) || localOllama
    if (!canFetch || (typedKey && typedKey.length < 8)) {
      setModelError(null)
      return undefined
    }
    const timer = setTimeout(() => {
      setModelsLoading(true)
      setModelError(null)
      listProviderModels({
        provider: form.provider,
        api_key: typedKey || undefined,
        base_url: form.base_url.trim() || undefined,
      })
        .then((r) => setCatalog((c) => rememberModels(c, form.provider, r.models)))
        .catch((e) => setModelError(e.message))
        .finally(() => setModelsLoading(false))
    }, 500)
    return () => clearTimeout(timer)
  }, [form.provider, form.api_key, form.base_url, settings])

  async function activateProvider(provider) {
    if (!settings || settings.llm_provider === provider || activating) return
    setActivating(provider)
    setNotice(null)
    try {
      setSettings(await saveSettings({ llm_provider: provider }))
      setNotice({ type: 'ok', text: `${providerLabel(provider)} is now the active provider.` })
    } catch (e) {
      setNotice({ type: 'error', text: e.message })
    } finally {
      setActivating(null)
    }
  }

  async function testProvider(provider) {
    setTesting(provider)
    setTestResults((r) => ({ ...r, [provider]: null }))
    try {
      const result = await listProviderModels({ provider })
      setCatalog((c) => rememberModels(c, provider, result.models))
      setTestResults((r) => ({
        ...r,
        [provider]: { ok: true, text: `Connected · ${result.models.length} models` },
      }))
    } catch (e) {
      setTestResults((r) => ({
        ...r,
        [provider]: { ok: false, text: e.message },
      }))
    } finally {
      setTesting(null)
    }
  }

  async function removeProvider(provider) {
    const target = PROVIDER_MAP[provider]
    const oauthTarget = target.value === 'claude' && settings?.claude_oauth_connected
    const message = oauthTarget
      ? `Remove the saved ${target.label} API key and sign out of the subscription?`
      : `Remove the saved ${target.label} API key?`
    if (!window.confirm(message)) return
    setNotice(null)
    try {
      const s = await deleteProvider(provider)
      setSettings(s)
      setCatalog((c) => forgetModels(c, provider))
      setTestResults((r) => {
        const next = { ...r }
        delete next[provider]
        return next
      })
      if (form.provider === provider) fillForm(provider, s)
      setNotice({ type: 'ok', text: `${target.label} key removed.` })
    } catch (e) {
      setNotice({ type: 'error', text: e.message })
    }
  }

  async function handleAddKey(e) {
    e.preventDefault()
    setNotice(null)
    const savedKey = isProviderConfigured(settings, spec)
    if (!form.api_key.trim() && !savedKey
        && !(spec.value === 'ollama' && form.base_url.trim())) {
      setNotice({ type: 'error', text: `Paste a ${spec.label} API key first.` })
      return
    }
    const payload = {
      [spec.baseUrlField]: form.base_url.trim(),
      [spec.modelField]: form.model,
    }
    if (form.api_key.trim()) payload[spec.keyField] = form.api_key.trim()
    if (!settings?.llm_provider || settings.llm_provider === 'mock') {
      payload.llm_provider = form.provider
    }
    setSaving(true)
    try {
      const s = await saveSettings(payload)
      setSettings(s)
      fillForm(form.provider, s)
      setNotice({ type: 'ok', text: `${spec.label} settings saved.` })
      const r = await listProviderModels({ provider: form.provider })
      setCatalog((c) => rememberModels(c, form.provider, r.models))
    } catch (e) {
      setNotice({ type: 'error', text: e.message })
    } finally {
      setSaving(false)
    }
  }

  async function handleOAuthStart() {
    setOauthError(null)
    setOauthNotice(null)
    // Open the tab inside the click handler so pop-up blockers allow it.
    const tab = window.open('about:blank', '_blank')
    try {
      const flow = await startClaudeOAuth()
      setOauthFlow(flow)
      setOauthCode('')
      if (tab) tab.location.href = flow.authorize_url
      else setOauthError('Allow pop-ups to open the Claude sign-in page.')
    } catch (e) {
      if (tab) tab.close()
      setOauthError(e.message)
    }
  }

  async function handleOAuthExchange(e) {
    e.preventDefault()
    if (!oauthFlow || !oauthCode.trim() || oauthBusy) return
    setOauthBusy(true)
    setOauthError(null)
    try {
      const s = await exchangeClaudeOAuth({
        code: oauthCode.trim(),
        state: oauthFlow.state,
        code_verifier: oauthFlow.code_verifier,
      })
      setSettings(s)
      setOauthFlow(null)
      setOauthCode('')
      setOauthNotice({ type: 'ok', text: 'Claude subscription connected.' })
      fillForm('claude', s)
      listProviderModels({ provider: 'claude' })
        .then((r) => setCatalog((c) => rememberModels(c, 'claude', r.models)))
        .catch((err) => setModelError(err.message))
    } catch (err) {
      setOauthError(err.message)
    } finally {
      setOauthBusy(false)
    }
  }

  async function handleOAuthDisconnect() {
    if (!window.confirm('Sign out of the Claude subscription?')) return
    setOauthError(null)
    setOauthNotice(null)
    try {
      const s = await disconnectClaudeOAuth()
      setSettings(s)
      setOauthFlow(null)
      setOauthCode('')
      setCatalog((c) => forgetModels(c, 'claude'))
      fillForm('claude', s)
      setOauthNotice({ type: 'ok', text: 'Signed out of the Claude subscription.' })
    } catch (e) {
      setOauthError(e.message)
    }
  }

  async function handleSaveLinkedin(e) {
    e.preventDefault()
    setNotice(null)
    setSavingLinkedin(true)
    try {
      const s = await saveSettings({ linkedin_url: linkedin.trim() })
      setSettings(s)
      setNotice({ type: 'ok', text: 'LinkedIn URL saved.' })
    } catch (e) {
      setNotice({ type: 'error', text: e.message })
    } finally {
      setSavingLinkedin(false)
    }
  }

  const configured = settings
    ? PROVIDERS.filter((p) => isProviderConfigured(settings, p) || settings.llm_provider === p.value)
    : []

  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-bold mb-6">Settings</h1>

      <section className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-xl">
        <div className="px-6 py-5 border-b border-gray-200 dark:border-gray-700 flex items-start gap-3">
          <div className="mt-0.5">{chipIcon}</div>
          <div>
            <h2 className="text-lg font-semibold">Model providers</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Claude, Ollama Cloud, Opencode Zen, Opencode Go or a local Ollama daemon.
              Several can coexist.
            </p>
          </div>
        </div>

        <div className="p-5 space-y-4">
          {configured.length === 0 && (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              No keys saved yet. Add one below — the mock provider keeps working without a key.
            </p>
          )}

          {configured.map((p) => {
            const active = settings?.llm_provider === p.value
            const mask = settings?.[p.keyField]
            const subscribed = p.value === 'claude' && claudeConnected
            const result = testResults[p.value]
            return (
              <div
                key={p.value}
                role="button"
                tabIndex={0}
                aria-label={`Make ${p.label} the active provider`}
                onClick={() => activateProvider(p.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    activateProvider(p.value)
                  }
                }}
                className={`flex flex-wrap items-center gap-3 rounded-lg border px-4 py-3 cursor-pointer transition-colors ${
                  active
                    ? 'border-indigo-500/70 bg-indigo-50/60 dark:bg-indigo-950/30 dark:border-indigo-500/60'
                    : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                }`}
              >
                <span className="rounded-full border border-indigo-500/40 bg-indigo-50 dark:bg-indigo-950/40 px-3 py-1 text-sm text-indigo-700 dark:text-indigo-200">
                  {p.label}
                </span>
                <span className={`font-mono text-sm ${mask || subscribed ? 'text-gray-700 dark:text-gray-300' : 'text-red-500'}`}>
                  {subscribed ? 'subscription sign-in' : (mask || 'no key saved')}
                </span>
                {active && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-green-500/40 bg-green-50 dark:bg-green-950/30 px-2.5 py-1 text-xs font-medium text-green-700 dark:text-green-300">
                    <span aria-hidden="true">✓</span> active
                  </span>
                )}

                <div className="ml-auto flex items-center gap-3">
                  {result && (
                    <span className={`text-xs ${result.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
                      {result.text}
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); activateProvider(p.value) }}
                    disabled={active || activating !== null}
                    title={active
                      ? `${p.label} is already the active provider`
                      : `Make ${p.label} the active provider`}
                    aria-label={`Use ${p.label} as the active provider`}
                    className="text-sm font-medium text-indigo-600 dark:text-indigo-300 hover:text-indigo-700 dark:hover:text-indigo-200 disabled:cursor-not-allowed disabled:text-gray-400 disabled:hover:text-gray-400 dark:disabled:text-gray-400 dark:disabled:hover:text-gray-400"
                  >
                    {activating === p.value ? 'Using…' : 'Use'}
                  </button>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); testProvider(p.value) }}
                    disabled={testing === p.value}
                    className="text-sm text-gray-600 dark:text-gray-300 hover:text-indigo-600 dark:hover:text-indigo-300 disabled:opacity-50"
                  >
                    {testing === p.value ? 'Testing…' : 'Test'}
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete ${p.label} key`}
                    title={`Delete ${p.label} key`}
                    onClick={(e) => { e.stopPropagation(); removeProvider(p.value) }}
                    className="rounded-md border border-red-500/40 p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30"
                  >
                    {trashIcon}
                  </button>
                </div>
              </div>
            )
          })}

          <form onSubmit={handleAddKey}
            className="rounded-lg border border-dashed border-gray-300 dark:border-gray-600 p-4 space-y-3">
            {spec.value === 'claude' && (
              <div className="rounded-lg border border-indigo-200 dark:border-indigo-500/40 bg-indigo-50/40 dark:bg-indigo-950/20 p-3 space-y-2">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium">Claude subscription</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Sign in with a Claude Pro/Max plan instead of an API key.
                    </p>
                  </div>
                  {claudeConnected ? (
                    <span className="inline-flex items-center gap-1 rounded-full border border-green-500/40 bg-green-50 dark:bg-green-950/30 px-2.5 py-1 text-xs font-medium text-green-700 dark:text-green-300">
                      <span aria-hidden="true">✓</span> signed in
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={handleOAuthStart}
                      className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700"
                    >
                      Sign in with Claude
                    </button>
                  )}
                </div>

                {claudeConnected && (
                  <div className="flex flex-wrap items-center gap-3 text-xs text-gray-600 dark:text-gray-300">
                    <span>
                      {settings?.claude_oauth_account || 'Claude subscription'}
                      {settings?.claude_oauth_expires_at
                        ? ` · token refreshes automatically (access expires ${formatExpiry(settings.claude_oauth_expires_at)})`
                        : ' · token refreshes automatically'}
                    </span>
                    <button
                      type="button"
                      onClick={handleOAuthDisconnect}
                      className="font-medium text-red-500 hover:underline"
                    >
                      Disconnect
                    </button>
                  </div>
                )}

                {oauthFlow && (
                  <div className="space-y-2">
                    <p className="text-xs text-gray-600 dark:text-gray-300">
                      Approve access in the new tab, copy the code Claude shows, and paste it here.
                    </p>
                    <div className="flex flex-wrap items-center gap-2">
                      <input
                        value={oauthCode}
                        onChange={(e) => setOauthCode(e.target.value)}
                        placeholder="Paste the code (code#state)"
                        autoComplete="off"
                        className="min-w-[12rem] flex-1 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                      />
                      <button
                        type="button"
                        onClick={handleOAuthExchange}
                        disabled={oauthBusy || !oauthCode.trim()}
                        className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                      >
                        {oauthBusy ? 'Connecting…' : 'Connect'}
                      </button>
                      <button
                        type="button"
                        onClick={() => { setOauthFlow(null); setOauthCode('') }}
                        className="rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                {oauthError && <p className="text-xs text-red-500">{oauthError}</p>}
                {oauthNotice && (
                  <p className={`text-xs ${oauthNotice.type === 'error' ? 'text-red-500' : 'text-green-600 dark:text-green-400'}`}>
                    {oauthNotice.text}
                  </p>
                )}
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-12 gap-3 items-end">
              <div className="lg:col-span-2">
                <label htmlFor="provider" className="block text-xs tracking-wide text-gray-500 dark:text-gray-400 mb-1 uppercase">
                  Provider
                </label>
                <select
                  id="provider"
                  value={form.provider}
                  onChange={(e) => fillForm(e.target.value)}
                  className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                >
                  {PROVIDERS.map((p) => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </select>
              </div>

              <div className="lg:col-span-2">
                <label htmlFor="api-key" className="block text-xs tracking-wide text-gray-500 dark:text-gray-400 mb-1 uppercase">
                  API Key
                </label>
                <input
                  id="api-key"
                  type="password"
                  autoComplete="off"
                  value={form.api_key}
                  onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value }))}
                  placeholder={settings?.[spec.keyField] ? 'Saved key' : spec.keyPlaceholder}
                  className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                />
              </div>

              <div className="lg:col-span-3">
                <label htmlFor="base-url" className="block text-xs tracking-wide text-gray-500 dark:text-gray-400 mb-1 uppercase">
                  Base URL (optional)
                </label>
                <input
                  id="base-url"
                  type="url"
                  value={form.base_url}
                  onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
                  placeholder={spec.basePlaceholder}
                  className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                />
              </div>

              <div className="lg:col-span-3">
                <label htmlFor="default-model" className="block text-xs tracking-wide text-gray-500 dark:text-gray-400 mb-1 uppercase">
                  Default model
                </label>
                <ModelSelect
                  id="default-model"
                  value={form.model}
                  onChange={(model) => setForm((f) => ({ ...f, model }))}
                  options={models}
                  providerLabel={spec.label}
                  defaultOption={spec.defaultModel}
                  placeholder="Provider default"
                  loading={modelsLoading}
                  error={modelError}
                />
              </div>

              <div className="lg:col-span-2">
                <button
                  type="submit"
                  disabled={saving}
                  className="w-full inline-flex items-center justify-center gap-1.5 bg-indigo-600 text-white px-3 py-2 rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
                >
                  <span aria-hidden="true" className="text-base leading-none">+</span>
                  {saving ? 'Saving…' : 'Add key'}
                </button>
              </div>
            </div>

            <p className="text-xs text-gray-500 dark:text-gray-400">
              {modelsLoading
                ? 'Fetching models…'
                : modelError
                  ? <span className="text-red-500">{modelError}</span>
                  : models.length
                    ? `${models.length} models available — pick a default above.`
                    : isProviderConfigured(settings, spec)
                      ? 'Using the saved key. Leave the key blank to keep it.'
                      : 'Paste a key to load the model list.'}
            </p>
          </form>

          {notice && (
            <p className={`text-sm ${notice.type === 'error' ? 'text-red-500' : 'text-green-600 dark:text-green-400'}`}>
              {notice.text}
            </p>
          )}
        </div>
      </section>

      <section className="mt-6 bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-xl p-5">
        <h2 className="text-lg font-semibold mb-1">Profile</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          Optional LinkedIn URL used when generating a cover letter.
        </p>
        <form onSubmit={handleSaveLinkedin} className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[16rem]">
            <label htmlFor="linkedin" className="block text-xs tracking-wide text-gray-500 dark:text-gray-400 mb-1 uppercase">
              LinkedIn profile URL
            </label>
            <input
              id="linkedin"
              type="url"
              value={linkedin}
              onChange={(e) => setLinkedin(e.target.value)}
              placeholder="https://linkedin.com/in/…"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
            />
          </div>
          <button
            type="submit"
            disabled={savingLinkedin}
            className="bg-indigo-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
          >
            {savingLinkedin ? 'Saving…' : 'Save'}
          </button>
        </form>
      </section>
    </div>
  )
}

function providerLabel(value) {
  return PROVIDER_MAP[value]?.label || value
}

function formatExpiry(value) {
  if (!value) return ''
  const date = new Date(value.endsWith('Z') ? value : `${value}Z`)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString()
}
