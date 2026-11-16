export default function KeywordPanel({ coverage = 0, matched = [], missing = [] }) {
  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="font-semibold text-sm">ATS keyword coverage</h3>
        <span className="text-xs text-gray-500 dark:text-gray-400">{coverage}% of JD keywords</span>
      </div>
      <div className="h-2 w-full rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden mb-3">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            coverage >= 70 ? 'bg-green-500' : coverage >= 40 ? 'bg-yellow-500' : 'bg-red-500'
          }`}
          style={{ width: `${Math.max(0, Math.min(100, coverage))}%` }}
        />
      </div>
      <div className="space-y-2 text-xs">
        <div>
          <p className="text-gray-500 dark:text-gray-400 mb-1">Covered ({matched.length})</p>
          <div className="flex flex-wrap gap-1">
            {matched.length === 0 && <span className="text-gray-400">none yet</span>}
            {matched.map((kw) => (
              <span key={kw}
                className="px-2 py-0.5 rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                {kw}
              </span>
            ))}
          </div>
        </div>
        <div>
          <p className="text-gray-500 dark:text-gray-400 mb-1">Missing ({missing.length})</p>
          <div className="flex flex-wrap gap-1">
            {missing.length === 0 && <span className="text-gray-400">all covered</span>}
            {missing.map((kw) => (
              <span key={kw}
                className="px-2 py-0.5 rounded-full bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">
                {kw}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
