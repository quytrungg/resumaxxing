import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  exportCoverLetter, finalizeReview, generateCoverLetter, getReview,
  rescoreReview, saveCoverLetter, setSuggestionStatus,
} from '../api'
import ScoreGauge from '../components/ScoreGauge'
import ScoreHistory from '../components/ScoreHistory'
import KeywordPanel from '../components/KeywordPanel'
import SuggestionCard from '../components/SuggestionCard'
import CoverLetterPanel from '../components/CoverLetterPanel'
import { reviewLabel } from '../reviewLabel'

const EXPORT_OPTIONS = [
  { mode: 'polished', format: 'docx', label: 'Polished CV — Word', hint: 'LLM rewrite' },
  { mode: 'polished', format: 'pdf', label: 'Polished CV — PDF', hint: 'LLM rewrite' },
  { mode: 'quick', format: 'docx', label: 'Quick merge — Word', hint: 'accepted only' },
  { mode: 'quick', format: 'pdf', label: 'Quick merge — PDF', hint: 'accepted only' },
]

export default function ReviewPage() {
  const { id } = useParams()
  const [review, setReview] = useState(null)
  const [error, setError] = useState(null)
  const [deciding, setDeciding] = useState(false)
  const [rescoring, setRescoring] = useState(false)
  const [showJd, setShowJd] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [letter, setLetter] = useState('')
  const [letterBusy, setLetterBusy] = useState(false)
  const [letterSaved, setLetterSaved] = useState(false)

  useEffect(() => {
    getReview(id)
      .then((r) => { setReview(r); setLetter(r.cover_letter || '') })
      .catch((e) => setError(e.message))
  }, [id])

  async function handleDecide(suggestionId, status) {
    setDeciding(true)
    try {
      await setSuggestionStatus(id, suggestionId, status)
      setReview((r) => ({
        ...r,
        suggestions: r.suggestions.map((s) =>
          s.id === suggestionId ? { ...s, status } : s,
        ),
      }))
    } catch (e) {
      setError(e.message)
    } finally {
      setDeciding(false)
    }
  }

  async function handleRescore() {
    setRescoring(true)
    setError(null)
    try {
      const res = await rescoreReview(id)
      setReview((r) => ({
        ...r,
        current_score: res.score,
        keyword_coverage: res.keyword_coverage,
        matched_keywords: res.matched_keywords,
        missing_keywords: res.missing_keywords,
        score_history: res.history_entry
          ? [...(r.score_history || []), res.history_entry]
          : r.score_history,
      }))
    } catch (e) {
      setError(e.message)
    } finally {
      setRescoring(false)
    }
  }

  async function handleFinalize(format, mode) {
    setExportOpen(false)
    setExporting(true)
    setError(null)
    try {
      await finalizeReview(id, format, mode)
      const fresh = await getReview(id)
      setReview(fresh)
      setLetter(fresh.cover_letter || '')
    } catch (e) {
      setError(e.message)
    } finally {
      setExporting(false)
    }
  }

  async function handleGenerateLetter() {
    setLetterBusy(true)
    setLetterSaved(false)
    try {
      const { text } = await generateCoverLetter(id)
      setLetter(text)
    } catch (e) {
      setError(e.message)
    } finally {
      setLetterBusy(false)
    }
  }

  async function handleSaveLetter() {
    setLetterBusy(true)
    try {
      await saveCoverLetter(id, letter)
      setLetterSaved(true)
    } catch (e) {
      setError(e.message)
    } finally {
      setLetterBusy(false)
    }
  }

  async function handleExportLetter(format) {
    try {
      await exportCoverLetter(id, format)
    } catch (e) {
      setError(e.message)
    }
  }

  if (error) return <p className="text-red-600">{error}</p>
  if (!review) return <p className="text-gray-500">Loading…</p>

  const pending = review.suggestions.filter((s) => s.status === 'PENDING')
  const done = review.suggestions.filter((s) => s.status !== 'PENDING')

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">{reviewLabel(review)}</h1>
      <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-5 mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <ScoreGauge score={review.current_score} />
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            Model{' '}
            <span className="font-medium">{review.llm_provider || 'saved setting'}</span>
            {review.llm_model ? ` · ${review.llm_model}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleRescore}
            disabled={rescoring}
            title="Re-score the CV using your current accepted and rejected suggestions"
            aria-label="Re-evaluate CV score"
            className="flex items-center gap-1.5 px-3 py-2 text-sm border dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
          >
            <svg
              className={`h-4 w-4 ${rescoring ? 'animate-spin' : ''}`}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M21 12a9 9 0 1 1-2.64-6.36" />
              <path d="M21 3v6h-6" />
            </svg>
            {rescoring ? 'Re-evaluating…' : 'Re-evaluate'}
          </button>
          <button
            onClick={() => setShowJd((v) => !v)}
            className="px-3 py-2 text-sm border dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            {showJd ? 'Hide' : 'Show'} Job Description
          </button>
          <div className="relative">
            <button
              onClick={() => setExportOpen((v) => !v)}
              disabled={exporting}
              className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50"
            >
              {exporting ? 'Preparing…' : 'Apply & Download ▾'}
            </button>
            {exportOpen && (
              <div className="absolute right-0 mt-1 w-60 bg-white dark:bg-gray-800 border dark:border-gray-600 rounded-md shadow-lg z-10 overflow-hidden">
                {EXPORT_OPTIONS.map(({ mode, format, label, hint }) => (
                  <button
                    key={`${mode}-${format}`}
                    onClick={() => handleFinalize(format, mode)}
                    className="w-full text-left px-4 py-2 text-sm hover:bg-indigo-50 dark:hover:bg-gray-700"
                  >
                    {label} <span className="text-xs text-gray-400">{hint}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-4 mb-6">
        <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-4">
          <ScoreHistory history={review.score_history || []} />
        </div>
        <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-4">
          <KeywordPanel
            coverage={review.keyword_coverage}
            matched={review.matched_keywords || []}
            missing={review.missing_keywords || []}
          />
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
          <SuggestionCard key={s.id} suggestion={s} onDecide={handleDecide} disabled={deciding} />
        ))}
      </div>

      {done.length > 0 && (
        <>
          <h2 className="font-semibold mt-8 mb-3 text-gray-500">Decided ({done.length})</h2>
          <div className="space-y-3">
            {done.map((s) => (
              <SuggestionCard key={s.id} suggestion={s} onDecide={handleDecide} disabled={deciding} />
            ))}
          </div>
        </>
      )}

      <CoverLetterPanel
        letter={letter}
        onChange={(value) => { setLetter(value); setLetterSaved(false) }}
        onGenerate={handleGenerateLetter}
        onSave={handleSaveLetter}
        onExport={handleExportLetter}
        finalized={review.status === 'finalized'}
        busy={letterBusy}
        saved={letterSaved}
      />
    </div>
  )
}
