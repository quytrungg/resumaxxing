const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(BASE + path, options)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res
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

export async function finalizeReview(id, format) {
  const res = await request(`/reviews/${id}/finalize?format=${format}`, { method: 'POST' })
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `cv_optimized_${id}.${format}`
  a.click()
  URL.revokeObjectURL(url)
}
