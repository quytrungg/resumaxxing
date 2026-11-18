import { useState } from 'react'

function barColor(pct) {
  if (pct >= 70) return 'bg-green-500'
  if (pct >= 40) return 'bg-yellow-500'
  return 'bg-red-500'
}

function Chip({ requirement, selected, onSelect }) {
  const matched = requirement.matched
  const tone = matched
    ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
    : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
  const active = selected === requirement.canonical
  return (
    <button
      type="button"
      onClick={() => onSelect(active ? null : requirement.canonical)}
      title={requirement.quote || requirement.label}
      className={`px-2 py-0.5 rounded-full text-left ${tone} ${
        active ? 'ring-2 ring-offset-1 ring-gray-400 dark:ring-gray-500' : ''
      }`}
    >
      {requirement.label}
    </button>
  )
}

function Group({ title, items, onSelect, selected }) {
  const hits = items.filter((item) => item.matched).length
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <p className="text-gray-500 dark:text-gray-400">
          {title} <span className="text-gray-400">({hits}/{items.length})</span>
        </p>
      </div>
      <div className="flex flex-wrap gap-1">
        {items.map((item) => (
          <Chip
            key={item.canonical || item.label}
            requirement={item}
            selected={selected}
            onSelect={onSelect}
          />
        ))}
      </div>
    </div>
  )
}

/**
 * ATS coverage with the JD's real requirements.
 *
 * `requirements` carries the extracted list (must/nice split, per-item matched,
 * and the JD quote as evidence). The legacy `matched`/`missing` chip lists are
 * still rendered when a cached response predates the extraction columns.
 */
export default function KeywordPanel({
  coverage = 0,
  mustHaveCoverage = null,
  niceToHaveCoverage = null,
  requirements = [],
  matched = [],
  missing = [],
  onRefresh,
  refreshing = false,
}) {
  const [selected, setSelected] = useState(null)

  const must = requirements.filter((r) => r.importance !== 'nice')
  const nice = requirements.filter((r) => r.importance === 'nice')
  const split = must.length > 0 && nice.length > 0
  const detail = requirements.find((r) => r.canonical === selected)

  return (
    <div>
      <div className="flex items-baseline justify-between mb-2 gap-2">
        <h3 className="font-semibold text-sm">ATS keyword coverage</h3>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {coverage}% of JD requirements
          </span>
          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              disabled={refreshing}
              className="text-xs px-2 py-0.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
            >
              {refreshing ? 'Extracting…' : 'Refresh'}
            </button>
          )}
        </div>
      </div>

      <div className="h-2 w-full rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor(coverage)}`}
          style={{ width: `${Math.max(0, Math.min(100, coverage))}%` }}
        />
      </div>

      {split && (
        <div className="mt-2 space-y-1">
          {[
            { label: 'Must have', pct: mustHaveCoverage },
            { label: 'Nice to have', pct: niceToHaveCoverage },
          ].map((row) => (
            <div key={row.label}>
              <div className="flex justify-between text-[10px] uppercase tracking-wide text-gray-400">
                <span>{row.label}</span>
                <span>{row.pct == null ? '—' : `${row.pct}%`}</span>
              </div>
              <div className="h-1 w-full rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
                <div
                  className={`h-full rounded-full ${barColor(row.pct ?? 0)}`}
                  style={{ width: `${Math.max(0, Math.min(100, row.pct ?? 0))}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="space-y-2 text-xs mt-3">
        {requirements.length > 0 ? (
          <>
            {must.length > 0 && (
              <Group
                title="Must have"
                items={must}
                selected={selected}
                onSelect={setSelected}
              />
            )}
            {nice.length > 0 && (
              <Group
                title="Nice to have"
                items={nice}
                selected={selected}
                onSelect={setSelected}
              />
            )}
            <p className="text-[10px] text-gray-400 dark:text-gray-500">
              Click a keyword to see the line in the job description that asks for it.
            </p>
            {detail && (
              <div className="rounded-md border border-gray-200 bg-gray-50 p-2 dark:border-gray-700 dark:bg-gray-900">
                <p className="font-medium text-gray-700 dark:text-gray-200">
                  {detail.label}
                  {detail.category ? (
                    <span className="ml-1 font-normal text-gray-400">
                      · {detail.category}
                    </span>
                  ) : null}
                </p>
                {detail.quote ? (
                  <p className="mt-1 italic text-gray-600 dark:text-gray-400">
                    “{detail.quote}”
                  </p>
                ) : (
                  <p className="mt-1 text-gray-400">No JD line recorded.</p>
                )}
              </div>
            )}
          </>
        ) : (
          <>
            <div>
              <p className="text-gray-500 dark:text-gray-400 mb-1">
                Covered ({matched.length})
              </p>
              <div className="flex flex-wrap gap-1">
                {matched.length === 0 && <span className="text-gray-400">none yet</span>}
                {matched.map((kw) => (
                  <span
                    key={kw}
                    className="px-2 py-0.5 rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                  >
                    {kw}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <p className="text-gray-500 dark:text-gray-400 mb-1">
                Missing ({missing.length})
              </p>
              <div className="flex flex-wrap gap-1">
                {missing.length === 0 && <span className="text-gray-400">all covered</span>}
                {missing.map((kw) => (
                  <span
                    key={kw}
                    className="px-2 py-0.5 rounded-full bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                  >
                    {kw}
                  </span>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
