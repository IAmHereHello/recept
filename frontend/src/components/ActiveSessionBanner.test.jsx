import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { ActiveSessionBanner } from './ActiveSessionBanner'
import { api } from '../lib/api'
import { setUser } from '../lib/user'

vi.mock('../lib/api', () => ({
  api: { getActiveSession: vi.fn() },
}))

const ACTIVE = {
  session_id: 5,
  recipe_id: 1,
  recipe_name: 'Ovenschotel',
  cooked_by: 'rachel',
  current_step: 1,
  total_steps: 3,
  active_timer_remaining_seconds: null,
  estimated_remaining_seconds: 610,
}

async function renderBanner() {
  let result
  await act(async () => {
    result = render(<ActiveSessionBanner />)
  })
  return result
}

describe('ActiveSessionBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders nothing when no session is active', async () => {
    setUser('michael')
    api.getActiveSession.mockResolvedValue(null)
    const { container } = await renderBanner()

    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when the active session belongs to the current user', async () => {
    setUser('rachel')
    api.getActiveSession.mockResolvedValue(ACTIVE)
    const { container } = await renderBanner()

    expect(container).toBeEmptyDOMElement()
  })

  it('shows a banner with the estimated remaining minutes for the other user', async () => {
    setUser('michael')
    api.getActiveSession.mockResolvedValue(ACTIVE)
    await renderBanner()

    expect(screen.getByText(/Ovenschotel/)).toBeInTheDocument()
    expect(screen.getByText(/nog 11 minuten/)).toBeInTheDocument() // ceil(610/60) = 11
  })

  it('falls back to step progress when there is no time estimate', async () => {
    setUser('michael')
    api.getActiveSession.mockResolvedValue({ ...ACTIVE, estimated_remaining_seconds: null })
    await renderBanner()

    expect(screen.getByText(/stap 2 van 3/)).toBeInTheDocument()
  })

  it('polls again after the interval elapses', async () => {
    setUser('michael')
    api.getActiveSession.mockResolvedValue(ACTIVE)
    await renderBanner()

    expect(api.getActiveSession).toHaveBeenCalledTimes(1)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(17000)
    })
    expect(api.getActiveSession).toHaveBeenCalledTimes(2)
  })
})
