import { useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { api } from '../lib/api'
import { getUser } from '../lib/user'

// Runs once per full app load (mount only, empty deps) — on a hard refresh
// or fresh PWA launch, if the current user has their own cooking session in
// progress, jump straight back into it instead of leaving them on whatever
// page the app happened to start on. Deliberately does NOT re-check on every
// client-side navigation, so navigating elsewhere on purpose afterward isn't
// overridden.
export function CookingSessionRejoin() {
  const navigate = useNavigate()
  const location = useLocation()
  const me = getUser()

  useEffect(() => {
    if (!me) return
    api.getActiveSession().then(active => {
      if (!active || active.cooked_by !== me) return
      // Already inside some cooking-mode page — even a paired sibling's, if
      // that one happens to be more "recently active" than this one — is
      // already "back in your cooking flow"; CookingMode's own mount effect
      // is what validates/rejoins the specific session at that URL, so don't
      // yank the user to a different (sibling) recipe's cook page instead.
      if (/^\/recipes\/\d+\/cook$/.test(location.pathname)) return
      const cookPath = `/recipes/${active.recipe_id}/cook`
      navigate(`${cookPath}?session=${active.session_id}`, { replace: true })
    }).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return null
}
