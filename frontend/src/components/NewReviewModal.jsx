import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createReview, uploadCv } from '../api'

export default function NewReviewModal({ onClose }) {
  const navigate = useNavigate()
  const [cvFile, setCvFile] = useState(null)
  const [mode, setMode] = useState('text')
  const [jdText, setJdText] = useState('')
  const [jdUrl, setJdUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (cvFile) await uploadCv(cvFile)
      const review = await createReview(
        mode === 'url' ? { jd_url: jdUrl } : { jd_text: jdText },
      )
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
