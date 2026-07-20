import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import { getUser } from '../lib/user'
import { PhotoUploader } from '../components/PhotoUploader'
import { ChevronLeft, ChevronRight, Timer, X, Check } from 'lucide-react'

const TIMER_REGEX = /(\d+)\s*(minuten|minuut|min)\b/i

function parseTimerMinutes(text) {
  const match = text?.match(TIMER_REGEX)
  return match ? Number(match[1]) : null
}

function formatTime(totalSeconds) {
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatDuration(seconds) {
  if (seconds < 90) return `${Math.round(seconds)} sec`
  return `${Math.round(seconds / 60)} min`
}

const HEARTBEAT_INTERVAL_MS = 60000

export function CookingMode() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const sessionId = Number(searchParams.get('session'))

  const [recipe, setRecipe] = useState(null)
  const [stepIndex, setStepIndex] = useState(0)
  const [phase, setPhase] = useState('steps') // 'steps' | 'finish'
  const [timerEndAt, setTimerEndAt] = useState(null)
  const [remaining, setRemaining] = useState(0)
  const [timerDone, setTimerDone] = useState(false)
  const [showStaleDialog, setShowStaleDialog] = useState(false)
  const [groupSessions, setGroupSessions] = useState([])
  const [meanwhileIndex, setMeanwhileIndex] = useState(0)
  const [pendingConfirmation, setPendingConfirmation] = useState(null)
  const wakeLockRef = useRef(null)
  const audioCtxRef = useRef(null)
  const me = getUser()

  const mainSteps = (recipe?.steps || []).filter(s => s.track !== 'meanwhile')
  const meanwhileSteps = (recipe?.steps || []).filter(s => s.track === 'meanwhile')

  function restoreTimerFromSession(session) {
    if (session.timer_seconds == null || session.timer_started_at == null) return
    const startedMs = new Date(session.timer_started_at).getTime()
    const remainingMs = session.timer_seconds * 1000 - (Date.now() - startedMs)
    if (remainingMs > 0) {
      setTimerEndAt(Date.now() + remainingMs)
      setRemaining(Math.round(remainingMs / 1000))
      setTimerDone(false)
    } else {
      // Timer fully elapsed while we were away — clear it rather than show a
      // stuck "done" state for however long ago it actually finished.
      resetLocalTimer()
      api.clearTimer(sessionId).catch(() => {})
    }
  }

  useEffect(() => {
    // Reset per-session local state up front — switching to a sibling session
    // (via the paired-recipe tabs) reuses this same component instance, so a
    // timer left running from the PREVIOUS session must not bleed through
    // when the new one doesn't have one of its own.
    resetLocalTimer()
    setMeanwhileIndex(0)
    setPhase('steps')
    setShowStaleDialog(false)
    Promise.all([api.getRecipe(id), api.getSession(sessionId)]).then(([r, session]) => {
      setRecipe(r)
      if (session.finished_at) {
        navigate(`/recipes/${id}`, { replace: true })
        return
      }
      setStepIndex(session.current_step || 0)
      if (session.group_id) {
        api.getSessionGroup(session.group_id).then(setGroupSessions).catch(() => setGroupSessions([]))
      } else {
        setGroupSessions([])
      }
      if (session.is_stale) {
        setShowStaleDialog(true)
      } else {
        restoreTimerFromSession(session)
        setPendingConfirmation(session.pending_step_confirmation || null)
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, sessionId])

  // Heartbeat while this page is open and visible, so reading a step for a
  // while without pressing anything doesn't get treated as having walked away.
  useEffect(() => {
    if (showStaleDialog) return
    function ping() {
      if (document.visibilityState === 'visible') {
        api.touchSession(sessionId).catch(() => {})
      }
    }
    const interval = setInterval(ping, HEARTBEAT_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [sessionId, showStaleDialog])

  // Unlock audio playback on the first tap anywhere on the page — creating/
  // resuming the AudioContext requires a user gesture, and the alarm later
  // fires from a setInterval callback with no gesture of its own.
  useEffect(() => {
    function unlock() { getAudioContext() }
    document.addEventListener('pointerdown', unlock, { once: true })
    return () => document.removeEventListener('pointerdown', unlock)
  }, [])

  useEffect(() => {
    return () => audioCtxRef.current?.close?.()
  }, [])

  function getAudioContext() {
    if (!audioCtxRef.current) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext
      if (!AudioContextClass) return null
      audioCtxRef.current = new AudioContextClass()
    }
    if (audioCtxRef.current.state === 'suspended') {
      audioCtxRef.current.resume().catch(() => {})
    }
    return audioCtxRef.current
  }

  function playAlarm() {
    try {
      const ctx = getAudioContext()
      if (!ctx) return
      for (let i = 0; i < 3; i++) {
        const start = ctx.currentTime + i * 0.35
        const osc = ctx.createOscillator()
        const gain = ctx.createGain()
        osc.type = 'sine'
        osc.frequency.value = 880
        gain.gain.setValueAtTime(0.0001, start)
        gain.gain.exponentialRampToValueAtTime(0.5, start + 0.02)
        gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.25)
        osc.connect(gain)
        gain.connect(ctx.destination)
        osc.start(start)
        osc.stop(start + 0.3)
      }
    } catch {
      // Web Audio unavailable — skip the alert sound rather than crash.
    }
  }

  async function resumeStaleSession() {
    const session = await api.touchSession(sessionId).then(() => api.getSession(sessionId))
    restoreTimerFromSession(session)
    setPendingConfirmation(session.pending_step_confirmation || null)
    setShowStaleDialog(false)
  }

  async function endStaleSession() {
    await api.deleteSession(sessionId)
    navigate(`/recipes/${id}`, { replace: true })
  }

  useEffect(() => {
    let cancelled = false
    async function requestLock() {
      try {
        if (navigator.wakeLock) {
          wakeLockRef.current = await navigator.wakeLock.request('screen')
        }
      } catch {
        // Wake Lock not supported/denied — degrade gracefully, no screen-dim guarantee.
      }
    }
    requestLock()
    function handleVisibility() {
      if (document.visibilityState === 'visible' && !cancelled) requestLock()
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => {
      cancelled = true
      document.removeEventListener('visibilitychange', handleVisibility)
      wakeLockRef.current?.release?.()
    }
  }, [])

  useEffect(() => {
    if (!timerEndAt) return
    const interval = setInterval(() => {
      const secs = Math.max(0, Math.round((timerEndAt - Date.now()) / 1000))
      setRemaining(secs)
      if (secs === 0) {
        setTimerDone(true)
        clearInterval(interval)
        navigator.vibrate?.(500)
        playAlarm()
      }
    }, 250)
    return () => clearInterval(interval)
  }, [timerEndAt])

  function resetLocalTimer() {
    setTimerEndAt(null)
    setRemaining(0)
    setTimerDone(false)
  }

  async function startTimer(minutes) {
    getAudioContext() // warm/resume on this click so the later alarm can play unattended
    const seconds = minutes * 60
    await api.startTimer(sessionId, seconds)
    setTimerEndAt(Date.now() + seconds * 1000)
    setRemaining(seconds)
    setTimerDone(false)
    setMeanwhileIndex(0)
  }

  async function cancelTimer() {
    resetLocalTimer()
    await api.clearTimer(sessionId)
  }

  async function goToStep(index) {
    const updated = await api.advanceStep(sessionId, index)
    setStepIndex(index)
    resetLocalTimer()
    setMeanwhileIndex(0)
    setPendingConfirmation(updated?.pending_step_confirmation || null)
  }

  async function next() {
    if (stepIndex < mainSteps.length - 1) {
      await goToStep(stepIndex + 1)
    } else {
      setPhase('finish')
    }
  }

  function prev() {
    if (stepIndex > 0) goToStep(stepIndex - 1)
  }

  async function finish() {
    await api.finishCooking(sessionId)
    wakeLockRef.current?.release?.()
    navigate(`/recipes/${id}`)
  }

  async function respondToConfirmation(counted) {
    if (!pendingConfirmation) return
    await api.confirmStepTime(pendingConfirmation.log_id, counted)
    setPendingConfirmation(null)
  }

  function switchToSession(g) {
    if (g.session_id === sessionId) return
    navigate(`/recipes/${g.recipe_id}/cook?session=${g.session_id}`)
  }

  if (!recipe) return <div className="p-6 text-center text-gray-400">Laden...</div>

  const confirmationDialog = pendingConfirmation && (
    <div className="fixed inset-0 bg-black/40 z-[90] flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl p-5 w-full max-w-sm">
        <h2 className="text-base font-bold text-gray-900 mb-2">Tijd kloppend?</h2>
        <p className="text-sm text-gray-600 mb-5">
          Deze stap duurde {formatDuration(pendingConfirmation.seconds)}, normaal {formatDuration(pendingConfirmation.avg_seconds)}.
          Moet dit meetellen voor de gemiddelde tijd?
        </p>
        <div className="flex gap-3">
          <button
            onClick={() => respondToConfirmation(false)}
            className="flex-1 py-2.5 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 transition"
          >
            Nee
          </button>
          <button
            onClick={() => respondToConfirmation(true)}
            className="flex-1 bg-green-600 text-white py-2.5 rounded-xl text-sm font-medium hover:bg-green-700 transition"
          >
            Ja, meetellen
          </button>
        </div>
      </div>
    </div>
  )

  if (showStaleDialog) {
    return (
      <div className="fixed inset-0 bg-black/60 z-[100] flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl p-6 w-full max-w-sm">
          <h2 className="text-lg font-bold text-gray-900 mb-2">Kooksessie hervatten?</h2>
          <p className="text-sm text-gray-600 mb-6">
            Je kookte {recipe.name} maar was een tijdje afwezig. Wil je doorgaan waar je gebleven was?
          </p>
          <div className="flex gap-3">
            <button
              onClick={endStaleSession}
              className="flex-1 py-2.5 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 transition"
            >
              Nee, beëindig
            </button>
            <button
              onClick={resumeStaleSession}
              className="flex-1 bg-green-600 text-white py-2.5 rounded-xl text-sm font-medium hover:bg-green-700 transition"
            >
              Ja, doorgaan
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (phase === 'finish') {
    return (
      <div className="w-full p-4 max-w-lg mx-auto pb-24">
        {confirmationDialog}
        <h1 className="text-xl font-bold text-gray-900 mt-4 mb-2">Klaar met koken!</h1>
        <p className="text-sm text-gray-500 mb-6">Voeg eventueel een foto toe.</p>
        <PhotoUploader sessionId={sessionId} uploadedBy={me} />
        <button
          onClick={finish}
          className="w-full mt-6 bg-green-600 text-white py-3 rounded-xl text-sm font-medium hover:bg-green-700 transition flex items-center justify-center gap-2"
        >
          <Check size={16} /> Klaar
        </button>
      </div>
    )
  }

  const step = mainSteps[stepIndex]
  const timerMinutes = step.wait_time_minutes ?? parseTimerMinutes(step.description)
  const meanwhileStep = meanwhileSteps[meanwhileIndex]

  return (
    <div className="w-full p-4 max-w-lg mx-auto pb-24 min-h-screen flex flex-col">
      {confirmationDialog}

      {groupSessions.length > 1 && (
        <div className="flex gap-2 mb-3">
          {groupSessions.map(g => (
            <button
              key={g.session_id}
              onClick={() => switchToSession(g)}
              className={`flex-1 px-3 py-2 rounded-lg text-xs font-medium border transition truncate
                ${g.session_id === sessionId ? 'bg-green-600 text-white border-green-600' : 'bg-white text-gray-600 border-gray-200'}
                ${g.finished_at ? 'opacity-50' : ''}`}
            >
              {g.recipe_name}{g.finished_at ? ' ✓' : ''}
            </button>
          ))}
        </div>
      )}

      <div className="text-xs text-gray-400 mb-2">Stap {stepIndex + 1} van {mainSteps.length}</div>
      <h1 className="text-lg font-semibold text-gray-900 mb-6">{recipe.name}</h1>

      <div className="flex-1 flex items-center justify-center text-center px-2">
        <p className="text-xl text-gray-800">{step.description}</p>
      </div>

      {timerMinutes && !timerEndAt && (
        <button
          onClick={() => startTimer(timerMinutes)}
          className="flex items-center justify-center gap-2 border border-amber-300 bg-amber-50 text-amber-700 py-2.5 rounded-xl text-sm font-medium mb-4"
        >
          <Timer size={16} /> Start timer ({timerMinutes} min)
        </button>
      )}

      {timerEndAt && (
        <div className={`flex items-center justify-between gap-2 py-2.5 px-4 rounded-xl text-sm font-medium mb-4 ${timerDone ? 'bg-red-100 text-red-700 animate-pulse' : 'bg-amber-50 text-amber-700'}`}>
          <span className="flex items-center gap-2"><Timer size={16} /> {formatTime(remaining)}</span>
          <button onClick={cancelTimer}><X size={14} /></button>
        </div>
      )}

      {timerEndAt && meanwhileStep && (
        <div className="bg-sky-50 border border-sky-200 rounded-xl p-3 mb-4">
          <div className="text-xs font-medium text-sky-700 mb-1">Ondertussen</div>
          <p className="text-sm text-sky-900 mb-2">{meanwhileStep.description}</p>
          <div className="flex gap-3">
            <button
              type="button"
              disabled={meanwhileIndex === 0}
              onClick={() => setMeanwhileIndex(i => i - 1)}
              className="text-xs text-sky-600 font-medium disabled:opacity-40"
            >
              ← Vorige
            </button>
            <button
              type="button"
              disabled={meanwhileIndex >= meanwhileSteps.length - 1}
              onClick={() => setMeanwhileIndex(i => i + 1)}
              className="text-xs text-sky-600 font-medium disabled:opacity-40"
            >
              Volgende →
            </button>
          </div>
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={prev}
          disabled={stepIndex === 0}
          className="flex-1 flex items-center justify-center gap-1 border border-gray-200 py-3 rounded-xl text-sm font-medium text-gray-600 disabled:opacity-40 transition"
        >
          <ChevronLeft size={16} /> Vorige
        </button>
        <button
          onClick={next}
          className="flex-1 flex items-center justify-center gap-1 bg-green-600 text-white py-3 rounded-xl text-sm font-medium hover:bg-green-700 transition"
        >
          {stepIndex < mainSteps.length - 1 ? <>Volgende <ChevronRight size={16} /></> : 'Klaar met stappen'}
        </button>
      </div>
    </div>
  )
}
