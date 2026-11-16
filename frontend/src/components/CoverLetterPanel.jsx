export default function CoverLetterPanel({
  letter, onChange, onGenerate, onSave, onExport, finalized, busy, saved,
}) {
  const hasLetter = Boolean(letter && letter.trim())

  return (
    <section className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-5 mt-8">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div>
          <h2 className="font-semibold">Cover letter</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {finalized
              ? 'Generated from your tailored CV and this job description.'
              : 'Finalize the CV first to unlock cover letter generation.'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={onGenerate}
            disabled={!finalized || busy}
            className="px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? 'Working…' : hasLetter ? 'Regenerate' : 'Generate'}
          </button>
          <button
            onClick={onSave}
            disabled={!hasLetter || busy}
            className="px-3 py-1.5 text-xs font-medium border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
          >
            Save
          </button>
          {['docx', 'pdf'].map((fmt) => (
            <button
              key={fmt}
              onClick={() => onExport(fmt)}
              disabled={!hasLetter || busy}
              className="px-3 py-1.5 text-xs font-medium border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
            >
              {fmt === 'docx' ? 'Download Word' : 'Download PDF'}
            </button>
          ))}
        </div>
      </div>
      {hasLetter ? (
        <textarea
          value={letter}
          onChange={(e) => onChange(e.target.value)}
          className="w-full h-72 border dark:border-gray-600 dark:bg-gray-900 rounded-md p-3 text-sm font-mono"
        />
      ) : (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          No cover letter yet.
        </p>
      )}
      {saved && <span className="text-xs text-green-600">Saved.</span>}
    </section>
  )
}
