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

export async function setSuggestionStatus(reviewId, suggestionId, status) {
  return (await request(`/reviews/${reviewId}/suggestions/${suggestionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })).json()
}

export async function rescoreReview(id) {
  return (await request(`/reviews/${id}/rescore`, { method: 'POST' })).json()
}

export async function finalizeReview(id, format, mode = 'polished') {
  const res = await request(
    `/reviews/${id}/finalize?format=${format}&mode=${mode}`,
    { method: 'POST' },
  )
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
