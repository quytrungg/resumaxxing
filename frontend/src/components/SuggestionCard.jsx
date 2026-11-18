import { useState } from 'react'
import DiffViewer, { DiffMethod } from 'react-diff-viewer-continued'
import { useDarkMode } from '../theme'

const STYLES = {
  ADD: { border: 'border-green-300 dark:border-green-700', bg: 'bg-green-50 dark:bg-green-950', badge: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200', label: '+ ADD' },
  REMOVE: { border: 'border-red-300 dark:border-red-700', bg: 'bg-red-50 dark:bg-red-950', badge: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200', label: '- REMOVE' },
  UPDATE: { border: 'border-yellow-300 dark:border-yellow-700', bg: 'bg-yellow-50 dark:bg-yellow-950', badge: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200', label: '~ UPDATE' },
}

const EDITABLE_TYPES = ['ADD', 'UPDATE']

function PencilIcon() {
  return (
    <svg
      className="h-4 w-4"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  )
}

export default function SuggestionCard({
  suggestion, onDecide, onSaveText, onResetText, disabled,
}) {
  const s = STYLES[suggestion.type] ?? STYLES.UPDATE
  const dark = useDarkMode()
  const decided = suggestion.status !== 'PENDING'
  const editable = EDITABLE_TYPES.includes(suggestion.type)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(suggestion.suggested_text)
  const [saving, setSaving] = useState(false)
  const trimmed = draft.trim()
  const canSave = trimmed.length > 0 && trimmed !== suggestion.suggested_text

  function startEditing() {
    setDraft(suggestion.suggested_text)
    setEditing(true)
  }

  async function handleSave() {
    if (!canSave || disabled) return
    setSaving(true)
    try {
      await onSaveText(suggestion.id, trimmed)
      setEditing(false)
    } catch {
      // The page surfaces the error; keep the editor open so the draft survives.
    } finally {
      setSaving(false)
    }
  }

  async function handleReset() {
    setSaving(true)
    try {
      await onResetText(suggestion.id)
      setEditing(false)
    } catch {
      // Same as above: stay in the editor.
    } finally {
      setSaving(false)
    }
  }

  function handleKeyDown(event) {
    if (event.key === 'Escape') {
      event.preventDefault()
      setEditing(false)
    } else if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault()
      handleSave()
    }
  }

  return (
    <div className={`border rounded-lg overflow-hidden ${s.border} ${decided ? 'opacity-60' : ''}`}>
      <div className={`flex items-center justify-between px-3 py-2 ${s.bg}`}>
        <div className="flex items-center gap-2 text-sm">
          <span className={`px-2 py-0.5 rounded text-xs font-semibold ${s.badge}`}>{s.label}</span>
          {suggestion.target_section && (
            <span className="text-gray-600 dark:text-gray-300">{suggestion.target_section}</span>
          )}
          {suggestion.original_suggested_text !== null && suggestion.original_suggested_text !== undefined && (
            <span className="text-xs text-gray-500 dark:text-gray-400" title="You edited this suggestion">· edited</span>
          )}
          {decided && (
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400">— {suggestion.status}</span>
          )}
        </div>
        {decided ? (
          <button
            onClick={() => onDecide(suggestion.id, 'PENDING')}
            disabled={disabled}
            className="px-3 py-1 text-xs font-medium bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50"
            title="Return this suggestion to pending"
          >
            Undo
          </button>
        ) : (
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

      <div className="relative bg-white dark:bg-gray-900 text-sm">
        {editable && !editing && (
          <button
            onClick={startEditing}
            disabled={disabled}
            title="Edit this suggestion"
            aria-label="Edit suggestion"
            className="absolute right-2 top-2 z-10 p-1.5 rounded border border-gray-300 dark:border-gray-600 bg-white/90 dark:bg-gray-800/90 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50"
          >
            <PencilIcon />
          </button>
        )}

        {editing ? (
          <div className="p-3">
            <label htmlFor={`suggestion-text-${suggestion.id}`} className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
              Adjust the suggested text
            </label>
            <textarea
              id={`suggestion-text-${suggestion.id}`}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleKeyDown}
              rows={Math.min(12, Math.max(3, draft.split('\n').length + 1))}
              autoFocus
              className="w-full px-3 py-2 font-mono text-xs border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-950 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <div className="mt-2 flex items-center justify-end gap-2">
              {suggestion.original_suggested_text !== null && suggestion.original_suggested_text !== undefined && (
                <button
                  onClick={handleReset}
                  disabled={disabled || saving}
                  title="Restore the AI wording"
                  className="mr-auto px-3 py-1 text-xs font-medium text-gray-600 dark:text-gray-300 hover:underline disabled:opacity-50"
                >
                  Reset to AI text
                </button>
              )}
              <button
                onClick={() => setEditing(false)}
                disabled={saving}
                className="px-3 py-1 text-xs font-medium bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={disabled || saving || !canSave}
                title="Save (⌘/Ctrl + Enter)"
                className="px-3 py-1 text-xs font-medium bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        ) : suggestion.type === 'UPDATE' ? (
          <div className={editable ? 'pr-10' : ''}>
            <DiffViewer
              oldValue={suggestion.original_text ?? ''}
              newValue={suggestion.suggested_text}
              splitView={false}
              compareMethod={DiffMethod.WORDS}
              hideLineNumbers
              useDarkTheme={dark}
              styles={{ variables: { light: { diffViewerBackground: '#fff' } } }}
            />
          </div>
        ) : (
          <pre className={`px-4 py-3 pr-12 whitespace-pre-wrap font-mono text-xs ${
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
