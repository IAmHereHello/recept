import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { PersistentTimerBar } from './PersistentTimerBar'
import { api } from '../lib/api'
import { setUser } from '../lib/user'

vi.mock('../lib/api', () => ({
  api: { getInProgressSessions: vi.fn() },
}))

const MINE = {
  session_id: 5, recipe_id: 1, recipe_name: 'Aubergine', cooked_by: 'michael',
  current_step: 1, total_steps: 3, estimated_remaining_seconds: 610,
}
const THEIRS = { ...MINE, session_id: 6, recipe_id: 2, recipe_name: 'Soep', cooked_by: 'rachel' }

async function renderBar(initialEntry = '/') {
  let result
  await act(async () => {
    result = render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="*" element={<PersistentTimerBar />} />
        </Routes>
      </MemoryRouter>
    )
  })
  return result
}

describe('PersistentTimerBar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('renders nothing when no identity is set', async () => {
    api.getInProgressSessions.mockResolvedValue([MINE])
    const { container } = await renderBar()
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when none of the in-progress sessions belong to me', async () => {
    setUser('michael')
    api.getInProgressSessions.mockResolvedValue([THEIRS])
    const { container } = await renderBar()
    expect(container).toBeEmptyDOMElement()
  })

  it('shows my own other in-progress session with its estimated time', async () => {
    setUser('michael')
    api.getInProgressSessions.mockResolvedValue([MINE, THEIRS])
    await renderBar()

    expect(screen.getByText('Aubergine')).toBeInTheDocument()
    expect(screen.getByText(/nog 11 min/)).toBeInTheDocument()
    expect(screen.queryByText('Soep')).not.toBeInTheDocument()
  })

  it('falls back to step progress when there is no time estimate', async () => {
    setUser('michael')
    api.getInProgressSessions.mockResolvedValue([{ ...MINE, estimated_remaining_seconds: null }])
    await renderBar()

    expect(screen.getByText(/stap 2\/3/)).toBeInTheDocument()
  })

  it('excludes the session currently open in CookingMode itself', async () => {
    setUser('michael')
    api.getInProgressSessions.mockResolvedValue([MINE])
    const { container } = await renderBar('/recipes/1/cook?session=5')

    expect(container).toBeEmptyDOMElement()
  })

  it('still shows a different in-progress session while one is open in CookingMode', async () => {
    setUser('michael')
    const other = { ...MINE, session_id: 9, recipe_id: 3, recipe_name: 'Flatbread' }
    api.getInProgressSessions.mockResolvedValue([MINE, other])
    await renderBar('/recipes/1/cook?session=5')

    expect(screen.queryByText('Aubergine')).not.toBeInTheDocument()
    expect(screen.getByText('Flatbread')).toBeInTheDocument()
  })

  it('navigates to the session\'s cook page when tapped', async () => {
    const user = userEvent.setup()
    setUser('michael')
    api.getInProgressSessions.mockResolvedValue([MINE])
    await act(async () => {
      render(
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route path="/" element={<PersistentTimerBar />} />
            <Route path="/recipes/:id/cook" element={<div>Cooking page</div>} />
          </Routes>
        </MemoryRouter>
      )
    })

    await user.click(screen.getByText('Aubergine'))
    expect(await screen.findByText('Cooking page')).toBeInTheDocument()
  })

  it('polls again after the interval elapses', async () => {
    vi.useFakeTimers()
    setUser('michael')
    api.getInProgressSessions.mockResolvedValue([MINE])
    await renderBar()

    expect(api.getInProgressSessions).toHaveBeenCalledTimes(1)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000)
    })
    expect(api.getInProgressSessions).toHaveBeenCalledTimes(2)
    vi.useRealTimers()
  })
})
