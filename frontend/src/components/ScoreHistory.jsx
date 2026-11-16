const WIDTH = 240
const HEIGHT = 56
const PAD = 6

export default function ScoreHistory({ history }) {
  if (!history || history.length === 0) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        No score history yet — press Re-evaluate to start the chart.
      </p>
    )
  }

  const scores = history.map((h) => h.score)
  const min = Math.min(...scores)
  const max = Math.max(...scores)
  const span = Math.max(1, max - min)
  const stepX = scores.length > 1 ? (WIDTH - PAD * 2) / (scores.length - 1) : 0
  const toY = (score) => HEIGHT - PAD - ((score - min) / span) * (HEIGHT - PAD * 2)
  const points = scores.map((score, i) => [PAD + i * stepX, toY(score)])

  let path = `M ${points[0][0]} ${points[0][1]}`
  for (let i = 1; i < points.length; i += 1) {
    path += ` L ${points[i][0]} ${points[i - 1][1]} L ${points[i][0]} ${points[i][1]}`
  }

  const last = history[history.length - 1]

  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <h3 className="font-semibold text-sm">Score history</h3>
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {history.length} step{history.length === 1 ? '' : 's'} · now {last.score}%
        </span>
      </div>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full max-w-xs"
        role="img"
        aria-label={`Score history: ${scores.join(', ')}`}
      >
        <line
          x1={PAD} y1={HEIGHT - PAD} x2={WIDTH - PAD} y2={HEIGHT - PAD}
          className="stroke-gray-200 dark:stroke-gray-700" strokeWidth="1"
        />
        <path
          d={path}
          fill="none"
          strokeWidth="2"
          strokeLinejoin="round"
          className="stroke-indigo-500"
        />
        {points.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="2.5" className="fill-indigo-500">
            <title>{`${history[i].reason || 'decision'}: ${scores[i]}%`}</title>
          </circle>
        ))}
      </svg>
      <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
        {last.reason ? `Last: ${last.reason}` : ''}
      </p>
    </div>
  )
}
