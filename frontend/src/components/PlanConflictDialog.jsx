import { useState } from 'react'
import { api } from '../lib/api'

const DAY_LABELS = {
  mon: 'Maandag', tue: 'Dinsdag', wed: 'Woensdag', thu: 'Donderdag',
  fri: 'Vrijdag', sat: 'Zaterdag', sun: 'Zondag',
}

// Shown when a cooked / logged meal lands on a day that already holds a
// different, unlocked meal. `onClose(replaced: boolean)` fires once resolved.
export function PlanConflictDialog({ conflict, onClose }) {
  const [busy, setBusy] = useState(false)
  if (!conflict) return null

  async function replace() {
    setBusy(true)
    try {
      await api.setDay(conflict.week_start, conflict.day, {
        week_start: conflict.week_start,
        day: conflict.day,
        recipe_id: conflict.cooked_recipe_id,
        locked: false,
      })
      onClose(true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-[110] flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl p-5 w-full max-w-sm">
        <h2 className="text-base font-bold text-gray-900 mb-2">Dag al gepland</h2>
        <p className="text-sm text-gray-600 mb-5">
          {DAY_LABELS[conflict.day] || conflict.day} heeft al{' '}
          <strong>{conflict.existing_recipe_name}</strong> op de planning. Vervangen door{' '}
          <strong>{conflict.cooked_recipe_name}</strong>?
        </p>
        <div className="flex gap-3">
          <button
            onClick={() => onClose(false)}
            disabled={busy}
            className="flex-1 py-2.5 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 transition disabled:opacity-50"
          >
            Behouden
          </button>
          <button
            onClick={replace}
            disabled={busy}
            className="flex-1 bg-green-600 text-white py-2.5 rounded-xl text-sm font-medium hover:bg-green-700 transition disabled:opacity-50"
          >
            Vervangen
          </button>
        </div>
      </div>
    </div>
  )
}
