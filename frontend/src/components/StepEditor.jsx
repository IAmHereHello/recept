import { useRef, useState } from 'react'
import { GripVertical, X, ArrowRightLeft, ChevronUp, ChevronDown, Plus } from 'lucide-react'

let keyCounter = 0
function makeKey() {
  keyCounter += 1
  return `step-${Date.now()}-${keyCounter}`
}

export function newStep(track = 'main') {
  return { _key: makeKey(), description: '', wait_time_minutes: '', track }
}

// Converts steps coming back from the API (no client key, sort_order per
// track) into the shape this editor works with.
export function stepsFromApi(apiSteps) {
  return (apiSteps || [])
    .slice()
    .sort((a, b) => a.sort_order - b.sort_order)
    .map(s => ({
      _key: makeKey(),
      description: s.description,
      wait_time_minutes: s.wait_time_minutes ?? '',
      track: s.track === 'meanwhile' ? 'meanwhile' : 'main',
    }))
}

// Converts this editor's state back into the API payload shape, recomputing
// sort_order fresh per track from the current array order.
export function stepsToApi(steps) {
  const counters = { main: 0, meanwhile: 0 }
  return steps
    .filter(s => s.description.trim())
    .map(s => {
      counters[s.track] += 1
      return {
        sort_order: counters[s.track],
        description: s.description.trim(),
        wait_time_minutes: s.wait_time_minutes ? Number(s.wait_time_minutes) : null,
        track: s.track,
      }
    })
}

const TRACK_LABELS = { main: 'Hoofdstappen', meanwhile: 'Ondertussen' }

export function StepEditor({ steps, onChange }) {
  const [dragKey, setDragKey] = useState(null)
  const [dropTarget, setDropTarget] = useState(null) // { key, position: 'before'|'after' } | { track, position: 'end' }
  const [pasteOpen, setPasteOpen] = useState(false)
  const [pasteText, setPasteText] = useState('')
  const dragInfo = useRef(null)

  function update(key, patch) {
    onChange(steps.map(s => (s._key === key ? { ...s, ...patch } : s)))
  }

  function remove(key) {
    onChange(steps.filter(s => s._key !== key))
  }

  function addStep(track) {
    onChange([...steps, newStep(track)])
  }

  function moveTrack(key, track) {
    update(key, { track })
  }

  function moveWithinTrack(key, direction) {
    const track = steps.find(s => s._key === key)?.track
    const indices = steps.map((s, i) => (s.track === track ? i : null)).filter(i => i !== null)
    const pos = indices.indexOf(steps.findIndex(s => s._key === key))
    const swapWith = indices[pos + direction]
    if (swapWith === undefined) return
    const myIndex = steps.findIndex(s => s._key === key)
    const next = [...steps]
    ;[next[myIndex], next[swapWith]] = [next[swapWith], next[myIndex]]
    onChange(next)
  }

  function addPastedSteps() {
    const lines = pasteText.split(/\n\n+/).map(s => s.trim()).filter(Boolean)
    const added = lines.map(description => ({ ...newStep('main'), description }))
    onChange([...steps, ...added])
    setPasteText('')
    setPasteOpen(false)
  }

  function resolveDropTarget(clientX, clientY) {
    const el = document.elementFromPoint(clientX, clientY)
    const card = el?.closest('[data-step-key]')
    if (card) {
      const key = card.getAttribute('data-step-key')
      const rect = card.getBoundingClientRect()
      const position = clientY < rect.top + rect.height / 2 ? 'before' : 'after'
      return { key, position }
    }
    const zone = el?.closest('[data-track-zone]')
    if (zone) {
      return { track: zone.getAttribute('data-track-zone'), position: 'end' }
    }
    return null
  }

  function onHandlePointerDown(e, key) {
    e.currentTarget.setPointerCapture(e.pointerId)
    dragInfo.current = { pointerId: e.pointerId }
    setDragKey(key)
  }

  function onHandlePointerMove(e) {
    if (!dragInfo.current || dragInfo.current.pointerId !== e.pointerId) return
    const target = resolveDropTarget(e.clientX, e.clientY)
    setDropTarget(target)
  }

  function onHandlePointerUp(e) {
    if (!dragInfo.current || dragInfo.current.pointerId !== e.pointerId) return
    dragInfo.current = null
    const key = dragKey
    const target = dropTarget
    setDragKey(null)
    setDropTarget(null)
    if (!key || !target) return

    const fromIndex = steps.findIndex(s => s._key === key)
    if (fromIndex === -1) return
    const dragged = { ...steps[fromIndex] }
    const rest = steps.filter(s => s._key !== key)

    if (target.position === 'end') {
      dragged.track = target.track
      onChange([...rest, dragged])
      return
    }
    if (target.key === key) return
    const targetIndex = rest.findIndex(s => s._key === target.key)
    if (targetIndex === -1) return
    dragged.track = rest[targetIndex].track
    const insertAt = target.position === 'before' ? targetIndex : targetIndex + 1
    const next = [...rest]
    next.splice(insertAt, 0, dragged)
    onChange(next)
  }

  function renderTrack(track) {
    const list = steps.filter(s => s.track === track)
    return (
      <div data-track-zone={track} className="space-y-2 min-h-[2.5rem]">
        {list.length === 0 && (
          <p className="text-xs text-gray-400 italic py-2">
            {track === 'meanwhile' ? 'Sleep hier stappen die ondertussen kunnen.' : 'Nog geen stappen.'}
          </p>
        )}
        {list.map(step => (
          <div key={step._key}>
            {dropTarget?.key === step._key && dropTarget.position === 'before' && (
              <div className="h-1 bg-green-500 rounded-full mb-1" />
            )}
            <div
              data-step-key={step._key}
              className={`flex gap-2 items-start bg-white border border-gray-200 rounded-xl p-2.5 ${dragKey === step._key ? 'opacity-40' : ''}`}
            >
              <button
                type="button"
                onPointerDown={e => onHandlePointerDown(e, step._key)}
                onPointerMove={onHandlePointerMove}
                onPointerUp={onHandlePointerUp}
                style={{ touchAction: 'none' }}
                className="shrink-0 text-gray-300 hover:text-gray-500 cursor-grab active:cursor-grabbing mt-1.5"
                aria-label="Sleep om te herordenen"
              >
                <GripVertical size={16} />
              </button>
              <div className="flex-1 min-w-0 space-y-1.5">
                <textarea
                  value={step.description}
                  onChange={e => update(step._key, { description: e.target.value })}
                  rows={2}
                  placeholder="Beschrijf deze stap..."
                  className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 resize-none"
                />
                {track === 'main' && (
                  <input
                    type="number"
                    min="0"
                    value={step.wait_time_minutes}
                    onChange={e => update(step._key, { wait_time_minutes: e.target.value })}
                    placeholder="Wachttijd (min, optioneel)"
                    className="w-44 border border-gray-200 rounded-lg px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-green-500"
                  />
                )}
              </div>
              <div className="flex flex-col items-center gap-1 shrink-0">
                <div className="flex gap-0.5">
                  <button type="button" aria-label="Omhoog" onClick={() => moveWithinTrack(step._key, -1)} className="text-gray-300 hover:text-gray-600">
                    <ChevronUp size={14} />
                  </button>
                  <button type="button" aria-label="Omlaag" onClick={() => moveWithinTrack(step._key, 1)} className="text-gray-300 hover:text-gray-600">
                    <ChevronDown size={14} />
                  </button>
                </div>
                <button
                  type="button"
                  onClick={() => moveTrack(step._key, track === 'main' ? 'meanwhile' : 'main')}
                  title={track === 'main' ? 'Verplaats naar Ondertussen' : 'Verplaats naar Hoofdstappen'}
                  className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-green-600"
                >
                  <ArrowRightLeft size={11} />
                </button>
                <button type="button" aria-label="Verwijder stap" onClick={() => remove(step._key)} className="text-gray-300 hover:text-red-500">
                  <X size={14} />
                </button>
              </div>
            </div>
            {dropTarget?.key === step._key && dropTarget.position === 'after' && (
              <div className="h-1 bg-green-500 rounded-full mt-1" />
            )}
          </div>
        ))}
        {dropTarget?.track === track && dropTarget.position === 'end' && (
          <div className="h-1 bg-green-500 rounded-full" />
        )}
        <button
          type="button"
          onClick={() => addStep(track)}
          className="flex items-center gap-1 text-sm text-green-600 hover:text-green-700 font-medium"
        >
          <Plus size={14} /> Stap toevoegen
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-gray-900">{TRACK_LABELS.main}</h3>
          <button
            type="button"
            onClick={() => setPasteOpen(o => !o)}
            className="text-xs text-gray-400 hover:text-gray-600"
          >
            {pasteOpen ? 'Annuleren' : 'Plak meerdere stappen'}
          </button>
        </div>
        {pasteOpen && (
          <div className="mb-3">
            <textarea
              value={pasteText}
              onChange={e => setPasteText(e.target.value)}
              placeholder={'Verwarm de oven op 180°C.\n\nMeng de bloem met de suiker.\n\nBak 25 minuten goudbruin.'}
              rows={6}
              className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 resize-none mb-1"
            />
            <p className="text-xs text-gray-400 mb-2">Lege regel tussen stappen = nieuwe stap</p>
            <button
              type="button"
              onClick={addPastedSteps}
              disabled={!pasteText.trim()}
              className="text-sm text-green-600 hover:text-green-700 font-medium disabled:opacity-40"
            >
              Toevoegen aan hoofdstappen
            </button>
          </div>
        )}
        {renderTrack('main')}
      </div>

      <div>
        <h3 className="text-sm font-semibold text-gray-900 mb-2">{TRACK_LABELS.meanwhile}</h3>
        <p className="text-xs text-gray-400 mb-2">
          Stappen die je kunt doen terwijl je op een andere stap wacht (bijv. tijdens het bakken).
        </p>
        {renderTrack('meanwhile')}
      </div>
    </div>
  )
}
