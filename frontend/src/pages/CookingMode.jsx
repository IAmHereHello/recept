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

function playBeep() {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext
    const ctx = new AudioContextClass()
    const osc = ctx.createOscillator()
    osc.type = 'sine'
    osc.frequency.value = 880
    osc.connect(ctx.destination)
    osc.start()
    osc.stop(ctx.currentTime + 0.5)
  } catch {
    // Web Audio unavailable — skip the alert sound rather than crash.
  }
}

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
  const wakeLockRef = useRef(null)
  const me = getUser()

  useEffect(() => {
    Promise.all([api.getRecipe(id), api.getSession(sessionId)]).then(([r, session]) => {
      setRecipe(r)
      if (session.finished_at) {
        navigate(`/recipes/${id}`, { replace: true })
        return
      }
      setStepIndex(session.current_step || 0)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, sessionId])

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
        playBeep()
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
    const seconds = minutes * 60
    await api.startTimer(sessionId, seconds)
    setTimerEndAt(Date.now() + seconds * 1000)
    setRemaining(seconds)
    setTimerDone(false)
  }

  async function cancelTimer() {
    resetLocalTimer()
    await api.clearTimer(sessionId)
  }

  async function goToStep(index) {
    await api.advanceStep(sessionId, index)
    setStepIndex(index)
    resetLocalTimer()
  }

  async function next() {
    if (stepIndex < recipe.steps.length - 1) {
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

  if (!recipe) return <div className="p-6 text-center text-gray-400">Laden...</div>

  if (phase === 'finish') {
    return (
      <div className="p-4 max-w-lg mx-auto pb-24">
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

  const step = recipe.steps[stepIndex]
  const timerMinutes = parseTimerMinutes(step.description)

  return (
    <div className="p-4 max-w-lg mx-auto pb-24 min-h-screen flex flex-col">
      <div className="text-xs text-gray-400 mb-2">Stap {stepIndex + 1} van {recipe.steps.length}</div>
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
          {stepIndex < recipe.steps.length - 1 ? <>Volgende <ChevronRight size={16} /></> : 'Klaar met stappen'}
        </button>
      </div>
    </div>
  )
}
