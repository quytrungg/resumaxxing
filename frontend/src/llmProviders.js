export const PROVIDERS = [
  {
    value: 'claude',
    label: 'Claude',
    keyField: 'claude_key',
    baseUrlField: 'claude_base_url',
    modelField: 'claude_model',
    defaultBaseUrl: 'https://api.anthropic.com',
    defaultModel: 'claude-sonnet-4-5',
    keyPlaceholder: 'sk-ant-…',
    basePlaceholder: 'https://api.anthropic.com',
  },
  {
    value: 'ollama',
    label: 'Ollama Cloud',
    keyField: 'ollama_key',
    baseUrlField: 'ollama_base_url',
    modelField: 'ollama_model',
    defaultBaseUrl: 'https://ollama.com',
    defaultModel: 'gpt-oss:120b-cloud',
    keyPlaceholder: 'Ollama Cloud API key',
    basePlaceholder: 'https://ollama.com',
  },
  {
    value: 'opencode',
    label: 'Opencode Zen',
    keyField: 'opencode_key',
    baseUrlField: 'opencode_base_url',
    modelField: 'opencode_model',
    defaultBaseUrl: 'https://opencode.ai/zen',
    defaultModel: 'grok-code',
    keyPlaceholder: 'Opencode API key',
    basePlaceholder: 'https://opencode.ai/zen',
  },
  {
    value: 'opencode_go',
    label: 'Opencode Go',
    keyField: 'opencode_go_key',
    baseUrlField: 'opencode_go_base_url',
    modelField: 'opencode_go_model',
    defaultBaseUrl: 'https://opencode.ai/zen/go',
    defaultModel: 'glm-5.3',
    keyPlaceholder: 'Opencode Go API key',
    basePlaceholder: 'https://opencode.ai/zen/go',
  },
]

export const PROVIDER_MAP = Object.fromEntries(
  PROVIDERS.map((p) => [p.value, p]),
)

export function providerLabel(value) {
  return PROVIDER_MAP[value]?.label || value
}

const CATALOG_KEY = 'modelCatalog'

export function loadCatalog() {
  try {
    const parsed = JSON.parse(localStorage.getItem(CATALOG_KEY) || '{}')
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

export function saveCatalog(catalog) {
  localStorage.setItem(CATALOG_KEY, JSON.stringify(catalog))
}

export function rememberModels(catalog, provider, models) {
  const next = { ...catalog, [provider]: models }
  saveCatalog(next)
  return next
}

export function forgetModels(catalog, provider) {
  const next = { ...catalog }
  delete next[provider]
  saveCatalog(next)
  return next
}
