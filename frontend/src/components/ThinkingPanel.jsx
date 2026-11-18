import { useEffect, useMemo, useRef, useState } from 'react'

const STAGES = [
  { key: 'jd', label: 'Reading the job description' },
  { key: 'cv', label: 'Scanning your CV' },
  { key: 'requirements', label: 'Extracting ATS requirements' },
  { key: 'suggestions', label: 'Drafting suggestions' },
  { key: 'score', label: 'Scoring the match' },
]

function buildStages(events, error) {
  const seen = new Map()
  for (const event of events) {
    if (!event?.stage) continue
    if (event.type !== 'stage' && event.type !== 'delta') continue
    if (!seen.has(event.stage)) {
      seen.set(event.stage, {
        key: event.stage,
        label: event.label || event.stage,
        detail: '',
        thinking: '',
        composing: false,
      })
    }
    const stage = seen.get(event.stage)
    if (event.type === 'stage') {
      stage.label = event.label || stage.label
      stage.detail = event.text || ''
    } else if (event.kind === 'thinking') {
      stage.thinking += event.text
    } else if (event.kind === 'output') {
      stage.composing = true
    }
  }

  let activeKey = null
  if (!error) {
    for (const event of events) {
      if (event?.type === 'stage') activeKey = event.stage
    }
    const terminal = events.some((e) => e.type === 'done' || e.type === 'error')
    if (terminal) activeKey = null
  }

  const ordered = STAGES.map((stage, index) => {
    const found = seen.get(stage.key)
    const active = stage.key === activeKey
    let status = 'pending'
    if (found) status = active ? 'active' : 'done'
    if (found && !activeKey) status = 'done'
    return {
      ...stage,
      detail: found?.detail || '',
      thinking: found?.thinking || '',
      composing: found?.composing || false,
      status,
      index,
    }
  })

  // A stage the server invented (future-proofing) still renders at the end.
  for (const [key, stage] of seen) {
    if (!STAGES.some((s) => s.key === key)) {
      ordered.push({ key, index: ordered.length, status: 'done', ...stage })
    }
  }

  return { stages: ordered, activeKey }
}

// `created_at` is a naive UTC timestamp with microseconds; normalise to a
// JS-parseable UTC instant instead of letting Date treat it as local time.
function parseServerTime(value) {
  if (!value) return Date.now()
  let iso = value
  if (!/[zZ]|[+-]\d{2}:?\d{2}$/.test(iso)) iso += 'Z'
  iso = iso.replace(/(\.\d{3})\d+/, '$1')
  const parsed = new Date(iso).getTime()
  return Number.isNaN(parsed) ? Date.now() : parsed
}

function Marker({ status }) {
  if (status === 'done') {
    return (
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300">
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M20 6 9 17l-5-5" />
        </svg>
      </span>
    )
  }
  if (status === 'active') {
    return (
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300">
        <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
          <path d="M21 12a9 9 0 1 1-6.22-8.56" />
        </svg>
      </span>
    )
  }
  return (
    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 border-gray-300 text-xs text-gray-400 dark:border-gray-600" aria-hidden="true" />
  )
}

export default function ThinkingPanel({ events = [], provider, model, startedAt, error }) {
  const { stages, activeKey } = useMemo(() => buildStages(events, error), [events, error])
  const [elapsed, setElapsed] = useState(0)
  const scrollRef = useRef(null)
  const stickRef = useRef(true)

  useEffect(() => {
    const started = parseServerTime(startedAt)
    const tick = () => setElapsed(Math.max(0, Math.round((Date.now() - started) / 1000)))
    tick()
    const timer = setInterval(tick, 500)
    return () => clearInterval(timer)
  }, [startedAt])

  const activeStage = stages.find((stage) => stage.key === activeKey)
  const transcript = activeStage ? `${activeStage.thinking}${activeStage.composing ? '…' : ''}` : ''

  useEffect(() => {
    const node = scrollRef.current
    if (node && stickRef.current) node.scrollTop = node.scrollHeight
  }, [transcript, activeKey])

  function handleScroll(e) {
    const node = e.currentTarget
    stickRef.current = node.scrollHeight - node.scrollTop - node.clientHeight < 48
  }

  return (
    <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <svg className="h-4 w-4 animate-spin text-indigo-600 dark:text-indigo-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
            <path d="M21 12a9 9 0 1 1-6.22-8.56" />
          </svg>
          <h2 className="font-semibold">
            {error ? 'Analysis failed' : 'Analyzing your CV'}
          </h2>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          <span className="font-medium">{provider || 'saved setting'}</span>
          {model ? ` · ${model}` : ''} · {elapsed}s
        </p>
      </div>

      <ol className="mt-5 space-y-4">
        {stages.map((stage) => {
          const isActive = stage.key === activeKey
          return (
            <li key={stage.key}>
              <div className="flex items-start gap-3">
                <Marker status={stage.status} />
                <div className="min-w-0">
                  <p className={`text-sm ${stage.status === 'pending' ? 'text-gray-400 dark:text-gray-500' : 'font-medium'}`}>
                    {stage.index + 1}. {stage.label}
                  </p>
                  {stage.detail && (
                    <p className="text-xs text-gray-500 dark:text-gray-400">{stage.detail}</p>
                  )}
                </div>
              </div>

              {isActive && (
                <div
                  ref={scrollRef}
                  onScroll={handleScroll}
                  className="mt-2 ml-9 max-h-56 overflow-y-auto rounded-md border border-gray-200 bg-gray-50 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-gray-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300"
                >
                  {stage.thinking || (stage.composing ? '' : 'Waiting for the model…')}
                  {stage.composing && (
                    <span className="text-indigo-600 dark:text-indigo-400">
                      {stage.thinking ? '\ncomposing the JSON payload…' : 'composing…'}
                    </span>
                  )}
                  {!error && <span className="ml-0.5 inline-block animate-pulse">▍</span>}
                </div>
              )}

              {isActive && !stage.thinking && !stage.composing && !error && (
                <p className="ml-9 mt-1 text-xs text-gray-400 dark:text-gray-500">
                  Token streaming appears here as the provider emits it.
                </p>
              )}
            </li>
          )
        })}
      </ol>

      {error && (
        <div className="mt-4 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
          <p className="font-medium">The model call failed</p>
          <p className="mt-1">{error}</p>
          <p className="mt-2 text-xs">
            Create a new review to retry. No partial suggestions were saved.
          </p>
        </div>
      )}

      <p className="mt-4 text-xs text-gray-400 dark:text-gray-500">
        Live view only — the transcript is not saved. The finished review appears
        as soon as the run completes.
      </p>
    </div>
  )
}
