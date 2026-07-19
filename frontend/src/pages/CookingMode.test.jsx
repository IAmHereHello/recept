import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { CookingMode } from './CookingMode'
import { api } from '../lib/api'
import { setUser } from '../lib/user'

vi.mock('../lib/api', () => ({
  api: {
    getRecipe: vi.fn(),
    getSession: vi.fn(),
    advanceStep: vi.fn(),
    startTimer: vi.fn(),
    clearTimer: vi.fn(),
    finishCooking: vi.fn(),
    uploadPhoto: vi.fn(),
    touchSession: vi.fn(),
    deleteSession: vi.fn(),
  },
}))

const RECIPE = {
  id: 1,
  name: 'Ovenschotel',
  steps: [
    { id: 1, description: 'Verwarm de oven voor.' },
    { id: 2, description: 'Bak 20 minuten in de oven.' },
  ],
}

const SESSION = { id: 5, current_step: 0, finished_at: null }

function stubWakeLock() {
  const release = vi.fn().mockResolvedValue(undefined)
  const request = vi.fn().mockResolvedValue({ release })
  vi.stubGlobal('navigator', Object.create(navigator, {
    wakeLock: { value: { request }, configurable: true },
  }))
  return { request, release }
}

function renderCookingMode() {
  return render(
    <MemoryRouter initialEntries={['/recipes/1/cook?session=5']}>
      <Routes>
        <Route path="/recipes/:id/cook" element={<CookingMode />} />
        <Route path="/recipes/:id" element={<div>Recipe detail page</div>} />
      </Routes>
    </MemoryRouter>
  )
}

describe('CookingMode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setUser('michael')
    api.getRecipe.mockResolvedValue(RECIPE)
    api.getSession.mockResolvedValue(SESSION)
    api.advanceStep.mockResolvedValue({})
    api.startTimer.mockResolvedValue({})
    api.clearTimer.mockResolvedValue(null)
    api.finishCooking.mockResolvedValue({})
    api.touchSession.mockResolvedValue(null)
    api.deleteSession.mockResolvedValue(null)
  })

  it('renders the first step and requests a wake lock on mount', async () => {
    const { request } = stubWakeLock()
    renderCookingMode()

    await screen.findByText('Stap 1 van 2')
    expect(screen.getByText('Ovenschotel')).toBeInTheDocument()
    expect(screen.getByText('Verwarm de oven voor.')).toBeInTheDocument()
    await waitFor(() => expect(request).toHaveBeenCalledWith('screen'))

    vi.unstubAllGlobals()
  })

  it('releases the wake lock on unmount', async () => {
    const { release } = stubWakeLock()
    const { unmount } = renderCookingMode()
    await screen.findByText('Stap 1 van 2')

    unmount()
    expect(release).toHaveBeenCalled()

    vi.unstubAllGlobals()
  })

  it('only shows a timer suggestion when the step text mentions minutes', async () => {
    stubWakeLock()
    const user = userEvent.setup()
    renderCookingMode()
    await screen.findByText('Stap 1 van 2')

    expect(screen.queryByText(/Start timer/)).not.toBeInTheDocument()

    await user.click(screen.getByText('Volgende'))
    await screen.findByText('Stap 2 van 2')

    expect(screen.getByText('Start timer (20 min)')).toBeInTheDocument()

    vi.unstubAllGlobals()
  })

  it('advances to the next step and calls the API with the new index', async () => {
    stubWakeLock()
    const user = userEvent.setup()
    renderCookingMode()
    await screen.findByText('Stap 1 van 2')

    await user.click(screen.getByText('Volgende'))

    expect(api.advanceStep).toHaveBeenCalledWith(5, 1)
    await screen.findByText('Bak 20 minuten in de oven.')

    vi.unstubAllGlobals()
  })

  it('disables "Vorige" on the first step', async () => {
    stubWakeLock()
    renderCookingMode()
    await screen.findByText('Stap 1 van 2')

    expect(screen.getByText('Vorige').closest('button')).toBeDisabled()

    vi.unstubAllGlobals()
  })

  it('shows the finish phase after the last step and completes cooking', async () => {
    stubWakeLock()
    const user = userEvent.setup()
    renderCookingMode()
    await screen.findByText('Stap 1 van 2')

    await user.click(screen.getByText('Volgende'))
    await screen.findByText('Stap 2 van 2')
    await user.click(screen.getByText('Klaar met stappen'))

    await screen.findByText('Klaar met koken!')

    await user.click(screen.getByRole('button', { name: /Klaar/ }))

    expect(api.finishCooking).toHaveBeenCalledWith(5)
    expect(await screen.findByText('Recipe detail page')).toBeInTheDocument()

    vi.unstubAllGlobals()
  })

  it('redirects back to the recipe if the session is already finished', async () => {
    stubWakeLock()
    api.getSession.mockResolvedValue({ id: 5, current_step: 0, finished_at: '2026-01-01T00:00:00' })
    renderCookingMode()

    expect(await screen.findByText('Recipe detail page')).toBeInTheDocument()

    vi.unstubAllGlobals()
  })

  it('restores an in-progress timer from the session on mount', async () => {
    stubWakeLock()
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T12:00:00.000Z'))
    const startedAt = new Date(Date.now() - 30000).toISOString() // started 30s ago
    api.getSession.mockResolvedValue({
      id: 5, current_step: 0, finished_at: null, is_stale: false,
      timer_seconds: 60, timer_started_at: startedAt,
    })

    await act(async () => { renderCookingMode() })

    expect(screen.getByText('0:30')).toBeInTheDocument()
    expect(api.clearTimer).not.toHaveBeenCalled()

    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('clears an already-elapsed timer instead of restoring it', async () => {
    stubWakeLock()
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T12:00:00.000Z'))
    const startedAt = new Date(Date.now() - 120000).toISOString() // 60s timer started 2 min ago
    api.getSession.mockResolvedValue({
      id: 5, current_step: 0, finished_at: null, is_stale: false,
      timer_seconds: 60, timer_started_at: startedAt,
    })

    await act(async () => { renderCookingMode() })

    expect(screen.queryByText(/^\d+:\d{2}$/)).not.toBeInTheDocument()
    expect(api.clearTimer).toHaveBeenCalledWith(5)

    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('shows a restart dialog for a stale session and resumes on confirm', async () => {
    stubWakeLock()
    const user = userEvent.setup()
    api.getSession.mockResolvedValueOnce({
      id: 5, current_step: 1, finished_at: null, is_stale: true,
      timer_seconds: null, timer_started_at: null,
    })
    renderCookingMode()

    await screen.findByText('Kooksessie hervatten?')
    expect(screen.queryByText('Stap 2 van 2')).not.toBeInTheDocument()

    api.getSession.mockResolvedValueOnce({
      id: 5, current_step: 1, finished_at: null, is_stale: false,
      timer_seconds: null, timer_started_at: null,
    })
    await user.click(screen.getByText('Ja, doorgaan'))

    expect(api.touchSession).toHaveBeenCalledWith(5)
    await screen.findByText('Stap 2 van 2')

    vi.unstubAllGlobals()
  })

  it('deletes the session and navigates away when ending a stale session', async () => {
    stubWakeLock()
    const user = userEvent.setup()
    api.getSession.mockResolvedValue({ id: 5, current_step: 0, finished_at: null, is_stale: true })
    renderCookingMode()

    await screen.findByText('Kooksessie hervatten?')
    await user.click(screen.getByText('Nee, beëindig'))

    expect(api.deleteSession).toHaveBeenCalledWith(5)
    expect(await screen.findByText('Recipe detail page')).toBeInTheDocument()

    vi.unstubAllGlobals()
  })
})
