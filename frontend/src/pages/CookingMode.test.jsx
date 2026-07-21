import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
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
    getSessionGroup: vi.fn(),
    confirmStepTime: vi.fn(),
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
    api.getSessionGroup.mockResolvedValue([])
    api.confirmStepTime.mockResolvedValue({})
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

  it('excludes meanwhile-track steps from the main step count and progression', async () => {
    stubWakeLock()
    api.getRecipe.mockResolvedValue({
      id: 1,
      name: 'Ovenschotel',
      steps: [
        { description: 'Verwarm de oven voor.', track: 'main' },
        { description: 'Bak 20 minuten in de oven.', track: 'main' },
        { description: 'Hak de groenten.', track: 'meanwhile' },
      ],
    })
    renderCookingMode()

    await screen.findByText('Stap 1 van 2')
    expect(screen.queryByText('Hak de groenten.')).not.toBeInTheDocument()

    vi.unstubAllGlobals()
  })

  it('shows a meanwhile suggestion while a timer is running, with its own prev/next', async () => {
    stubWakeLock()
    const user = userEvent.setup()
    api.getRecipe.mockResolvedValue({
      id: 1,
      name: 'Ovenschotel',
      steps: [
        { description: 'Bak 20 minuten in de oven.', track: 'main' },
        { description: 'Hak de groenten.', track: 'meanwhile' },
        { description: 'Was de sla.', track: 'meanwhile' },
      ],
    })
    renderCookingMode()
    await screen.findByText('Stap 1 van 1')

    expect(screen.queryByText('Ondertussen')).not.toBeInTheDocument()
    await user.click(screen.getByText('Start timer (20 min)'))

    expect(await screen.findByText('Ondertussen')).toBeInTheDocument()
    expect(screen.getByText('Hak de groenten.')).toBeInTheDocument()

    await user.click(screen.getByText('Volgende →'))
    expect(screen.getByText('Was de sla.')).toBeInTheDocument()

    vi.unstubAllGlobals()
  })

  it('prefers an explicit wait_time_minutes over parsing the description text', async () => {
    stubWakeLock()
    api.getRecipe.mockResolvedValue({
      id: 1,
      name: 'Ovenschotel',
      steps: [{ description: 'Laat rusten.', wait_time_minutes: 45, track: 'main' }],
    })
    renderCookingMode()

    expect(await screen.findByText('Start timer (45 min)')).toBeInTheDocument()

    vi.unstubAllGlobals()
  })

  it('shows a recipe switcher when the session belongs to a paired group', async () => {
    stubWakeLock()
    const user = userEvent.setup()
    api.getSession.mockResolvedValue({ id: 5, current_step: 0, finished_at: null, group_id: 9 })
    api.getSessionGroup.mockResolvedValue([
      { session_id: 5, recipe_id: 1, recipe_name: 'Ovenschotel', finished_at: null },
      { session_id: 6, recipe_id: 2, recipe_name: 'Flatbread', finished_at: null },
    ])
    renderCookingMode()

    await screen.findByText('Stap 1 van 2')
    const ownTab = screen.getByText('Ovenschotel', { selector: 'button' })
    const otherTab = screen.getByText('Flatbread')
    expect(ownTab).toBeInTheDocument()
    expect(otherTab).toBeInTheDocument()

    // Clicking the tab for the session already open is a no-op (no extra fetch).
    const callsBefore = api.getRecipe.mock.calls.length
    await user.click(ownTab)
    expect(api.getRecipe.mock.calls.length).toBe(callsBefore)

    // Clicking the other recipe's tab navigates there (same mocked route
    // re-renders CookingMode for that id in this test harness).
    await user.click(otherTab)
    expect(await screen.findByText('Stap 1 van 2')).toBeInTheDocument()

    vi.unstubAllGlobals()
  })

  it('clears a running timer when switching to a sibling session that has none of its own', async () => {
    stubWakeLock()
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T12:00:00.000Z'))
    const startedAt = new Date(Date.now() - 5000).toISOString() // 60s timer, 5s elapsed

    api.getSession.mockImplementation((sid) => Promise.resolve(
      sid === 5
        ? { id: 5, current_step: 0, finished_at: null, is_stale: false, group_id: 9, timer_seconds: 60, timer_started_at: startedAt }
        : { id: 6, current_step: 0, finished_at: null, is_stale: false, group_id: 9 }
    ))
    api.getSessionGroup.mockResolvedValue([
      { session_id: 5, recipe_id: 1, recipe_name: 'Ovenschotel', finished_at: null },
      { session_id: 6, recipe_id: 2, recipe_name: 'Flatbread', finished_at: null },
    ])

    await act(async () => { renderCookingMode() })
    expect(screen.getByText('0:55')).toBeInTheDocument()

    await act(async () => { fireEvent.click(screen.getByText('Flatbread')) })
    expect(screen.queryByText(/^\d+:\d{2}$/)).not.toBeInTheDocument()

    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('shows an outlier confirmation dialog after advancing a step and lets the user respond', async () => {
    stubWakeLock()
    const user = userEvent.setup()
    api.advanceStep.mockResolvedValue({
      pending_step_confirmation: { log_id: 42, track: 'main', sort_order: 1, seconds: 900, avg_seconds: 450 },
    })
    renderCookingMode()
    await screen.findByText('Stap 1 van 2')

    await user.click(screen.getByText('Volgende'))

    expect(await screen.findByText('Tijd kloppend?')).toBeInTheDocument()
    expect(screen.getByText(/15 min/)).toBeInTheDocument()
    expect(screen.getByText(/normaal.*8 min/)).toBeInTheDocument()

    await user.click(screen.getByText('Ja, meetellen'))
    expect(api.confirmStepTime).toHaveBeenCalledWith(42, true)
    expect(screen.queryByText('Tijd kloppend?')).not.toBeInTheDocument()

    vi.unstubAllGlobals()
  })

  it('surfaces a pending confirmation restored from the initial session fetch', async () => {
    stubWakeLock()
    const user = userEvent.setup()
    api.getSession.mockResolvedValue({
      id: 5, current_step: 0, finished_at: null, is_stale: false,
      pending_step_confirmation: { log_id: 7, track: 'main', sort_order: 1, seconds: 30, avg_seconds: 100 },
    })
    renderCookingMode()

    expect(await screen.findByText('Tijd kloppend?')).toBeInTheDocument()
    await user.click(screen.getByText('Nee'))

    expect(api.confirmStepTime).toHaveBeenCalledWith(7, false)
    expect(screen.queryByText('Tijd kloppend?')).not.toBeInTheDocument()

    vi.unstubAllGlobals()
  })

  it('quits cooking after confirmation, deleting the session and navigating away', async () => {
    stubWakeLock()
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderCookingMode()
    await screen.findByText('Stap 1 van 2')

    await user.click(screen.getByText('Stop met koken'))

    expect(window.confirm).toHaveBeenCalledWith(expect.stringMatching(/telt niet mee/))
    expect(api.deleteSession).toHaveBeenCalledWith(5)
    expect(await screen.findByText('Recipe detail page')).toBeInTheDocument()

    vi.unstubAllGlobals()
  })

  it('does not quit cooking when the confirmation is declined', async () => {
    stubWakeLock()
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderCookingMode()
    await screen.findByText('Stap 1 van 2')

    await user.click(screen.getByText('Stop met koken'))

    expect(api.deleteSession).not.toHaveBeenCalled()
    expect(screen.getByText('Stap 1 van 2')).toBeInTheDocument()

    vi.unstubAllGlobals()
  })

  it('does not show the quit-cooking button on the finish/photo phase', async () => {
    stubWakeLock()
    const user = userEvent.setup()
    renderCookingMode()
    await screen.findByText('Stap 1 van 2')

    await user.click(screen.getByText('Volgende'))
    await screen.findByText('Stap 2 van 2')
    await user.click(screen.getByText('Klaar met stappen'))

    await screen.findByText('Klaar met koken!')
    expect(screen.queryByText('Stop met koken')).not.toBeInTheDocument()

    vi.unstubAllGlobals()
  })
})
