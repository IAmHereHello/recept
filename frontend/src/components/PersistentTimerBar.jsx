import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { getUser } from '../lib/user'
import { Timer, ChefHat } from 'lucide-react'

const POLL_INTERVAL_MS = 15000

// Shows every OTHER in-progress cooking session belonging to the current
// user (e.g. the aubergine's oven timer while you're heads-down on the
// flatbread's steps) — pinned above the bottom Nav so it's visible from
// anywhere in the app, not just from inside CookingMode itself.
export function PersistentTimerBar() {
  const [sessions, setSessions] = useState([])
  const location = useLocation()
  const navigate = useNavigate()
  const me = getUser()

  useEffect(() => {
    let cancelled = false
    function poll() {
      api.getInProgressSessions().then(data => {
        if (!cancelled) setSessions(data)
      }).catch(() => {
        if (!cancelled) setSessions([])
      })
    }
    poll()
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  if (!me) return null

  const cookMatch = location.pathname.match(/^\/recipes\/\d+\/cook$/)
  const currentSessionId = cookMatch ? Number(new URLSearchParams(location.search).get('session')) : null

  const mine = sessions.filter(s => s.cooked_by === me && s.session_id !== currentSessionId)
  if (mine.length === 0) return null

  return (
    <div className="fixed bottom-16 left-0 right-0 z-40 px-3 pointer-events-none">
      <div className="max-w-lg mx-auto w-full flex flex-col gap-1.5">
        {mine.map(s => {
          const minutesLeft = s.estimated_remaining_seconds != null
            ? Math.ceil(s.estimated_remaining_seconds / 60)
            : null
          return (
            <button
              key={s.session_id}
              onClick={() => navigate(`/recipes/${s.recipe_id}/cook?session=${s.session_id}`)}
              className="pointer-events-auto w-full flex items-center justify-between gap-2 bg-gray-900/90 text-white text-xs font-medium px-3 py-2 rounded-xl shadow-lg"
            >
              <span className="flex items-center gap-1.5 truncate">
                <ChefHat size={14} className="shrink-0" /> {s.recipe_name}
              </span>
              <span className="flex items-center gap-1 shrink-0">
                <Timer size={12} />
                {minutesLeft != null ? `nog ${minutesLeft} min` : `stap ${s.current_step + 1}/${s.total_steps}`}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
