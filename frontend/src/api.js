const BASE = '/api'

export function getAppPassword() {
  return localStorage.getItem('appPassword') || ''
}

export function setAppPassword(password) {
  if (password) localStorage.setItem('appPassword', password)
  else localStorage.removeItem('appPassword')
}

function authHeaders() {
  const password = getAppPassword()
  return password ? { 'X-App-Password': password } : {}
}

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  })
  if (!res.ok) {
    if (res.status === 401) window.dispatchEvent(new Event('auth-required'))
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res
}

function download(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export async function getAuthStatus() {
  return (await fetch(`${BASE}/auth`)).json()
}

export async function getSettings() {
  return (await request('/settings')).json()
}

export async function saveSettings(data) {
  return (await request('/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })).json()
}

export async function listProviderModels({ provider, api_key, base_url }) {
  return (await request('/settings/providers/models', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider, api_key, base_url }),
  })).json()
}

export async function deleteProvider(provider) {
  return (await request(`/settings/providers/${provider}`, {
    method: 'DELETE',
  })).json()
}

export async function startClaudeOAuth() {
  return (await request('/settings/claude/oauth/start', {
    method: 'POST',
  })).json()
}

export async function exchangeClaudeOAuth({ code, state, code_verifier }) {
  return (await request('/settings/claude/oauth/exchange', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, state, code_verifier }),
  })).json()
}

export async function disconnectClaudeOAuth() {
  return (await request('/settings/claude/oauth', {
    method: 'DELETE',
  })).json()
}

export async function uploadCv(file) {
  const form = new FormData()
  form.append('file', file)
  return (await request('/cv/upload', { method: 'POST', body: form })).json()
}

export async function createReview(payload) {
  return (await request('/reviews', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })).json()
}

export async function listReviews() {
  return (await request('/reviews')).json()
}

export async function getReview(id) {
  return (await request(`/reviews/${id}`)).json()
}

/**
 * Tail a running review over SSE (fetch + reader, so X-App-Password works).
 * Calls `onEvent` per frame and settles on done/error. Falls back to polling
 * via `onError` when streaming is unavailable.
 */
export async function streamReviewEvents(id, { onEvent, signal, onError } = {}) {
  let res
  try {
    res = await request(`/reviews/${id}/events`, {
      signal,
      headers: { Accept: 'text/event-stream' },
    })
  } catch (e) {
    if (!signal?.aborted) onError?.(e)
    return
  }
  if (!res.body) {
    onError?.(new Error('Streaming is not supported by this browser'))
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const payload = frame
          .split('\n')
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trimStart())
          .join('\n')
        if (payload) {
          let event
          try {
            event = JSON.parse(payload)
          } catch {
            event = null // ignore malformed frame
          }
          if (event) {
            onEvent?.(event)
            if (event.type === 'done' || event.type === 'error') {
              reader.cancel().catch(() => {})
              return event
            }
          }
        }
        boundary = buffer.indexOf('\n\n')
      }
    }
  } catch (e) {
    if (!signal?.aborted) onError?.(e)
  }
}

export async function setSuggestionStatus(reviewId, suggestionId, status) {
  return (await request(`/reviews/${reviewId}/suggestions/${suggestionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })).json()
}

export async function updateSuggestionText(reviewId, suggestionId, text) {
  return (await request(`/reviews/${reviewId}/suggestions/${suggestionId}/text`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ suggested_text: text }),
  })).json()
}

export async function resetSuggestionText(reviewId, suggestionId) {
  return (await request(`/reviews/${reviewId}/suggestions/${suggestionId}/text`, {
    method: 'DELETE',
  })).json()
}

export async function rescoreReview(id) {
  return (await request(`/reviews/${id}/rescore`, { method: 'POST' })).json()
}

export async function finalizeReview(id, format) {
  const res = await request(`/reviews/${id}/finalize?format=${format}`, {
    method: 'POST',
  })
  download(await res.blob(), `cv_optimized_${id}.${format}`)
}

export async function generateCoverLetter(id) {
  return (await request(`/reviews/${id}/cover-letter`, { method: 'POST' })).json()
}

export async function saveCoverLetter(id, text) {
  return (await request(`/reviews/${id}/cover-letter`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })).json()
}

export async function exportCoverLetter(id, format) {
  const res = await request(`/reviews/${id}/cover-letter/export?format=${format}`, {
    method: 'POST',
  })
  download(await res.blob(), `cover_letter_${id}.${format}`)
}
