import { useEffect, useMemo, useRef, useState } from 'react'

const ROW_HEIGHT = 36

export default function ModelSelect({
  value,
  onChange,
  options = [],
  providerLabel = '',
  defaultOption = null,
  placeholder = 'Select a model',
  loading = false,
  error = null,
  allowCustom = true,
  disabled = false,
  id,
}) {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const [active, setActive] = useState(0)
  const [openUp, setOpenUp] = useState(false)
  const [maxHeight, setMaxHeight] = useState(420)
  const wrapRef = useRef(null)
  const triggerRef = useRef(null)
  const filterRef = useRef(null)

  function measure() {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return
    const below = window.innerHeight - rect.bottom - 16
    const above = rect.top - 16
    const up = below < 260 && above > below
    setOpenUp(up)
    setMaxHeight(Math.max(ROW_HEIGHT * 3, Math.min(420, up ? above : below)))
  }

  function openMenu() {
    if (disabled) return
    measure()
    setFilter('')
    setOpen(true)
  }

  function closeMenu() {
    setOpen(false)
  }

  function select(next) {
    onChange(next)
    closeMenu()
    triggerRef.current?.focus()
  }

  useEffect(() => {
    if (!open) return undefined
    const onPointerDown = (e) => {
      if (!wrapRef.current?.contains(e.target)) closeMenu()
    }
    const onKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        closeMenu()
        triggerRef.current?.focus()
      }
    }
    const onResize = () => measure()
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    window.addEventListener('resize', onResize)
    requestAnimationFrame(() => filterRef.current?.focus())
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('resize', onResize)
    }
  }, [open])

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase()
    if (!q) return options
    return options.filter((m) => m.toLowerCase().includes(q))
  }, [options, filter])

  const items = useMemo(() => {
    const rows = []
    if (defaultOption !== null) {
      rows.push({ value: '', label: `Default · ${defaultOption}`, noHint: true })
    }
    for (const model of filtered) rows.push({ value: model, label: model })
    const typed = filter.trim()
    if (allowCustom && typed && !options.includes(typed)) {
      rows.push({ value: typed, label: `Use “${typed}”` })
    }
    return rows
  }, [defaultOption, filtered, allowCustom, filter, options])

  useEffect(() => {
    if (!open) return
    const idx = items.findIndex((item) => item.value === value)
    setActive(idx >= 0 ? idx : 0)
  }, [open, filter])

  function handleKeyDown(e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((i) => Math.min(items.length - 1, i + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => Math.max(0, i - 1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (items[active]) select(items[active].value)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      closeMenu()
      triggerRef.current?.focus()
    }
  }

  return (
    <div className="relative" ref={wrapRef}>
      <button
        id={id}
        type="button"
        ref={triggerRef}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => (open ? closeMenu() : openMenu())}
        onKeyDown={(e) => {
          if (!open && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
            e.preventDefault()
            openMenu()
          }
        }}
        className="w-full flex items-center justify-between gap-2 border rounded-md px-3 py-2 text-sm text-left bg-white dark:bg-gray-900 dark:border-gray-600 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
      >
        <span className={value ? 'truncate' : 'truncate text-gray-400 dark:text-gray-500'}>
          {value || placeholder}
        </span>
        <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"
          className={`h-4 w-4 shrink-0 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`}>
          <path d="M6 8l4 4 4-4" stroke="currentColor" strokeWidth="1.6"
            strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <div
          style={{ maxWidth: 'min(32rem, calc(100vw - 2rem))' }}
          className={`absolute z-40 w-max min-w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-2xl overflow-hidden ${openUp ? 'bottom-full mb-1' : 'top-full mt-1'}`}
        >
          <div className="p-2 border-b border-gray-200 dark:border-gray-700">
            <input
              ref={filterRef}
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Filter models…"
              className="w-full rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
            />
          </div>
          <ul
            role="listbox"
            style={{ maxHeight }}
            className="overflow-y-auto py-1 text-sm [color-scheme:light] dark:[color-scheme:dark]"
          >
            {items.length === 0 && (
              <li className="px-3 py-2 text-gray-500 dark:text-gray-400">
                {loading ? 'Loading models…' : 'No models found.'}
              </li>
            )}
            {items.map((item, i) => {
              const selected = item.value === (value || '')
              return (
                <li
                  key={`${item.value}::${i}`}
                  role="option"
                  aria-selected={selected}
                  onMouseEnter={() => setActive(i)}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => select(item.value)}
                  className={`mx-1 flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 ${
                    i === active
                      ? 'bg-indigo-50 dark:bg-indigo-950/60'
                      : 'hover:bg-gray-100 dark:hover:bg-gray-800'
                  }`}
                >
                  <span className="w-4 shrink-0 text-indigo-600 dark:text-indigo-300">
                    {selected ? '✓' : ''}
                  </span>
                  <span className="whitespace-nowrap">{item.label}</span>
                  {!item.noHint && providerLabel && (
                    <span className="ml-auto shrink-0 text-xs text-gray-400 dark:text-gray-500">
                      · {providerLabel}
                    </span>
                  )}
                </li>
              )
            })}
          </ul>
          {error && (
            <p className="border-t border-gray-200 dark:border-gray-700 px-3 py-2 text-xs text-red-500">
              {error}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
