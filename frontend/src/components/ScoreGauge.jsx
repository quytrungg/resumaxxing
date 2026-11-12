export default function ScoreGauge({ score }) {
  const color = score >= 70 ? 'text-green-600' : score >= 40 ? 'text-yellow-600' : 'text-red-600'
  const ring = score >= 70 ? 'stroke-green-500' : score >= 40 ? 'stroke-yellow-500' : 'stroke-red-500'
  const r = 34
  const circumference = 2 * Math.PI * r
  const offset = circumference * (1 - score / 100)

  return (
    <div className="flex items-center gap-3">
      <svg width="88" height="88" viewBox="0 0 88 88">
        <circle cx="44" cy="44" r={r} fill="none" strokeWidth="8" className="stroke-gray-200 dark:stroke-gray-700" />
        <circle
          cx="44" cy="44" r={r} fill="none" strokeWidth="8"
          className={`${ring} transition-all duration-500`}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 44 44)"
        />
        <text x="44" y="50" textAnchor="middle" className={`${color} fill-current text-lg font-bold`}>
          {score}%
        </text>
      </svg>
      <div>
        <p className="text-sm text-gray-500 dark:text-gray-400">Match Score</p>
        <p className={`text-2xl font-bold ${color} transition-colors`}>{score}%</p>
      </div>
    </div>
  )
}
