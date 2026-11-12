import DiffViewer, { DiffMethod } from 'react-diff-viewer-continued'
import { useDarkMode } from '../theme'

const STYLES = {
  ADD: { border: 'border-green-300 dark:border-green-700', bg: 'bg-green-50 dark:bg-green-950', badge: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200', label: '+ ADD' },
  REMOVE: { border: 'border-red-300 dark:border-red-700', bg: 'bg-red-50 dark:bg-red-950', badge: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200', label: '- REMOVE' },
  UPDATE: { border: 'border-yellow-300 dark:border-yellow-700', bg: 'bg-yellow-50 dark:bg-yellow-950', badge: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200', label: '~ UPDATE' },
}

export default function SuggestionCard({ suggestion, onDecide, disabled }) {
  const s = STYLES[suggestion.type] ?? STYLES.UPDATE
  const dark = useDarkMode()
  const decided = suggestion.status !== 'PENDING'

  return (
    <div className={`border rounded-lg overflow-hidden ${s.border} ${decided ? 'opacity-60' : ''}`}>
      <div className={`flex items-center justify-between px-3 py-2 ${s.bg}`}>
        <div className="flex items-center gap-2 text-sm">
          <span className={`px-2 py-0.5 rounded text-xs font-semibold ${s.badge}`}>{s.label}</span>
          {suggestion.target_section && (
            <span className="text-gray-600 dark:text-gray-300">{suggestion.target_section}</span>
          )}
          {decided && (
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400">— {suggestion.status}</span>
          )}
        </div>
        {!decided && (
          <div className="flex gap-2">
            <button
              onClick={() => onDecide(suggestion.id, 'ACCEPTED')}
              disabled={disabled}
              className="px-3 py-1 text-xs font-medium bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
            >
              Accept
            </button>
            <button
              onClick={() => onDecide(suggestion.id, 'REJECTED')}
              disabled={disabled}
              className="px-3 py-1 text-xs font-medium bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50"
            >
              Reject
            </button>
          </div>
        )}
      </div>

      <div className="bg-white dark:bg-gray-900 text-sm">
        {suggestion.type === 'UPDATE' ? (
          <DiffViewer
            oldValue={suggestion.original_text ?? ''}
            newValue={suggestion.suggested_text}
            splitView={false}
            compareMethod={DiffMethod.WORDS}
            hideLineNumbers
            useDarkTheme={dark}
            styles={{ variables: { light: { diffViewerBackground: '#fff' } } }}
          />
        ) : (
          <pre className={`px-4 py-3 whitespace-pre-wrap font-mono text-xs ${
            suggestion.type === 'ADD' ? 'bg-green-50 text-green-900 dark:bg-green-950 dark:text-green-100' : 'bg-red-50 text-red-900 line-through dark:bg-red-950 dark:text-red-100'
          }`}>
            {suggestion.type === 'ADD' ? '+ ' : '- '}
            {suggestion.type === 'ADD' ? suggestion.suggested_text : suggestion.original_text ?? suggestion.suggested_text}
          </pre>
        )}
        {suggestion.reasoning && (
          <p className="px-4 py-2 text-xs text-gray-500 dark:text-gray-400 border-t dark:border-gray-700">Why: {suggestion.reasoning}</p>
        )}
      </div>
    </div>
  )
}
