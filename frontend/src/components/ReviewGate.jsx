import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { getUser } from '../lib/user'
import { StarRating } from './StarRating'
import { ChefHat, Loader2 } from 'lucide-react'

export function ReviewGate() {
  const [queue, setQueue] = useState(null) // null = not checked yet
  const [stars, setStars] = useState(0)
  const [saving, setSaving] = useState(false)
  const me = getUser()

  useEffect(() => {
    if (!me) { setQueue([]); return }
    api.getPendingReviews(me).then(setQueue).catch(() => setQueue([]))
  }, [me])

  if (!queue || queue.length === 0) return null

  const current = queue[0]

  async function submit() {
    if (stars === 0 || saving) return
    setSaving(true)
    try {
      await api.rateSession(current.id, { user: me, stars })
      setQueue(q => q.slice(1))
      setStars(0)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-[100] flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl p-6 w-full max-w-sm">
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
          onClick={submit}
          disabled={stars === 0 || saving}
          className="w-full bg-green-600 text-white py-2.5 rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50 transition flex items-center justify-center gap-2"
        >
          {saving && <Loader2 size={14} className="animate-spin" />}
          Opslaan {queue.length > 1 ? `(nog ${queue.length - 1})` : ''}
        </button>
      </div>
    </div>
  )
}
