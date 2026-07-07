import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { getUser } from '../lib/user'
import { ChefHat } from 'lucide-react'

const POLL_INTERVAL_MS = 17000

export function ActiveSessionBanner() {
  const [active, setActive] = useState(null)
  const me = getUser()

  useEffect(() => {
    let cancelled = false
    function poll() {
      api.getActiveSession().then(data => {
        if (!cancelled) setActive(data)
      }).catch(() => {
        if (!cancelled) setActive(null)
      })
    }
    poll()
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  if (!active || !me || active.cooked_by === me) return null

  const minutesLeft = active.estimated_remaining_seconds != null
    ? Math.ceil(active.estimated_remaining_seconds / 60)
    : null

  return (
    <div className="fixed top-0 left-0 right-0 z-40 bg-amber-100 text-amber-800 text-xs font-medium px-4 py-2 text-center">
      <span className="flex items-center justify-center gap-1.5">
        <ChefHat size={14} />
        Koken van {active.recipe_name} in uitvoering
        {minutesLeft != null
          ? ` — nog ${minutesLeft} minuten`
          : ` — stap ${active.current_step + 1} van ${active.total_steps}`}
      </span>
    </div>
  )
}
