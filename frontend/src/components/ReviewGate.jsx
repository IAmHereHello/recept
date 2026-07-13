import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { getUser } from '../lib/user'
import { StarRating } from './StarRating'
import { ChefHat, Loader2, Snowflake } from 'lucide-react'

export function ReviewGate() {
  const [queue, setQueue] = useState(null) // null = not checked yet
  const [stars, setStars] = useState(0)
  const [saving, setSaving] = useState(false)
  const [phase, setPhase] = useState('rating') // 'rating' | 'freezer'
  const [freezerPortions, setFreezerPortions] = useState('')
  const [freezerExpiresAt, setFreezerExpiresAt] = useState('')
  const [freezerSaving, setFreezerSaving] = useState(false)
  const me = getUser()

  useEffect(() => {
    if (!me) { setQueue([]); return }
    api.getPendingReviews(me).then(setQueue).catch(() => setQueue([]))
  }, [me])

  if (!queue || queue.length === 0) return null

  const current = queue[0]

  function advanceQueue() {
    setQueue(q => q.slice(1))
    setStars(0)
    setPhase('rating')
    setFreezerPortions('')
    setFreezerExpiresAt('')
  }

  async function submitRating() {
    if (stars === 0 || saving) return
    setSaving(true)
    try {
      await api.rateSession(current.id, { user: me, stars })
      if (current.is_freezable) {
        setFreezerPortions(current.portions != null ? String(current.portions) : '')
        setPhase('freezer')
      } else {
        advanceQueue()
      }
    } finally {
      setSaving(false)
    }
  }

  async function submitFreezer() {
    if (freezerSaving) return
    setFreezerSaving(true)
    try {
      const portions = Number(freezerPortions)
      if (portions > 0) {
        await api.createFreezerItem({
          recipe_id: current.recipe_id,
          cook_session_id: current.id,
          portions_total: portions,
          added_by: me,
          ...(freezerExpiresAt ? { expires_at: freezerExpiresAt } : {}),
        })
      }
      advanceQueue()
    } finally {
      setFreezerSaving(false)
    }
  }

  function skipFreezer() {
    advanceQueue()
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-[100] flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl p-6 w-full max-w-sm">
        {phase === 'rating' ? (
          <>
            <div className="flex items-center gap-2 mb-1 text-green-600">
              <ChefHat size={20} />
              <span className="text-xs font-semibold uppercase tracking-wide">Gekookt!</span>
            </div>
            <h2 className="text-lg font-bold text-gray-900 mb-1">{current.recipe_name}</h2>
            <p className="text-sm text-gray-500 mb-4">
              {new Date(current.cooked_at).toLocaleDateString('nl-NL', { day: 'numeric', month: 'long', year: 'numeric' })}
            </p>
            <p className="text-sm text-gray-600 mb-3">Hoe vond je dit gerecht?</p>
            <div className="mb-6">
              <StarRating value={stars} onChange={setStars} size={8} />
            </div>
            <button
              onClick={submitRating}
              disabled={stars === 0 || saving}
              className="w-full bg-green-600 text-white py-2.5 rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50 transition flex items-center justify-center gap-2"
            >
              {saving && <Loader2 size={14} className="animate-spin" />}
              Opslaan {queue.length > 1 ? `(nog ${queue.length - 1})` : ''}
            </button>
          </>
        ) : (
          <>
            <div className="flex items-center gap-2 mb-1 text-sky-600">
              <Snowflake size={20} />
              <span className="text-xs font-semibold uppercase tracking-wide">Vriezer</span>
            </div>
            <h2 className="text-lg font-bold text-gray-900 mb-1">{current.recipe_name}</h2>
            <p className="text-sm text-gray-600 mb-4">Nog iets over voor de vriezer? Hoeveel porties?</p>
            <input
              type="number"
              min="1"
              value={freezerPortions}
              onChange={e => setFreezerPortions(e.target.value)}
              placeholder="Aantal porties"
              className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-sky-500"
            />
            <details className="mb-4">
              <summary className="text-xs text-gray-400 cursor-pointer">THT aanpassen</summary>
              <input
                type="date"
                value={freezerExpiresAt}
                onChange={e => setFreezerExpiresAt(e.target.value)}
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm mt-2"
              />
            </details>
            <div className="flex gap-3">
              <button
                onClick={skipFreezer}
                disabled={freezerSaving}
                className="flex-1 py-2.5 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 transition disabled:opacity-50"
              >
                Overslaan
              </button>
              <button
                onClick={submitFreezer}
                disabled={freezerSaving || !freezerPortions}
                className="flex-1 bg-sky-600 text-white py-2.5 rounded-xl text-sm font-medium hover:bg-sky-700 disabled:opacity-50 transition flex items-center justify-center gap-2"
              >
                {freezerSaving && <Loader2 size={14} className="animate-spin" />}
                Bewaren
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
