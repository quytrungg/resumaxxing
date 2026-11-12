import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { finalizeReview, getReview, setSuggestionStatus } from '../api'
import ScoreGauge from '../components/ScoreGauge'
import SuggestionCard from '../components/SuggestionCard'

export default function ReviewPage() {
  const { id } = useParams()
  const [review, setReview] = useState(null)
  const [error, setError] = useState(null)
  const [scoring, setScoring] = useState(false)
  const [showJd, setShowJd] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)

  useEffect(() => {
    getReview(id).then(setReview).catch((e) => setError(e.message))
  }, [id])

  async function handleDecide(suggestionId, status) {
    setScoring(true)
    try {
      const { score } = await setSuggestionStatus(id, suggestionId, status)
      setReview((r) => ({
        ...r,
        current_score: score,
        suggestions: r.suggestions.map((s) =>
          s.id === suggestionId ? { ...s, status } : s,
        ),
      }))
    } catch (e) {
      setError(e.message)
    } finally {
      setScoring(false)
    }
  }

  if (error) return <p className="text-red-600">{error}</p>
  if (!review) return <p className="text-gray-500">Loading…</p>

  const pending = review.suggestions.filter((s) => s.status === 'PENDING')
  const done = review.suggestions.filter((s) => s.status !== 'PENDING')

  return (
    <div>
      <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-5 mb-6 flex items-center justify-between">
        <ScoreGauge score={review.current_score} />
        <div className="flex items-center gap-3">
          {scoring && <span className="text-xs text-gray-400">rescoring…</span>}
          <button
            onClick={() => setShowJd((v) => !v)}
            className="px-3 py-2 text-sm border dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            {showJd ? 'Hide' : 'Show'} Job Description
          </button>
          <div className="relative">
            <button
              onClick={() => setExportOpen((v) => !v)}
              className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
            >
              Apply &amp; Download ▾
            </button>
            {exportOpen && (
              <div className="absolute right-0 mt-1 w-48 bg-white dark:bg-gray-800 border dark:border-gray-600 rounded-md shadow-lg z-10">
                {[
                  { fmt: 'docx', label: 'Word (.docx)', hint: 'editable' },
                  { fmt: 'pdf', label: 'PDF (.pdf)', hint: 'ready to send' },
                ].map(({ fmt, label, hint }) => (
                  <button
                    key={fmt}
                    onClick={() => { setExportOpen(false); finalizeReview(id, fmt) }}
                    className="w-full text-left px-4 py-2 text-sm hover:bg-indigo-50 dark:hover:bg-gray-700 first:rounded-t-md last:rounded-b-md"
                  >
                    {label} <span className="text-xs text-gray-400">{hint}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {showJd && (
        <pre className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-4 mb-6 text-sm whitespace-pre-wrap max-h-72 overflow-y-auto">
          {review.jd_text}
        </pre>
      )}

      <h2 className="font-semibold mb-3">
        Suggestions <span className="text-gray-400 font-normal">({pending.length} pending)</span>
      </h2>
      <div className="space-y-3">
        {pending.map((s) => (
          <SuggestionCard key={s.id} suggestion={s} onDecide={handleDecide} disabled={scoring} />
        ))}
      </div>

      {done.length > 0 && (
        <>
          <h2 className="font-semibold mt-8 mb-3 text-gray-500">Decided ({done.length})</h2>
          <div className="space-y-3">
            {done.map((s) => (
              <SuggestionCard key={s.id} suggestion={s} onDecide={handleDecide} disabled={scoring} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
