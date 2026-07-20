import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { CookingSessionRejoin } from './CookingSessionRejoin'
import { api } from '../lib/api'
import { setUser } from '../lib/user'

vi.mock('../lib/api', () => ({
  api: { getActiveSession: vi.fn() },
}))

const ACTIVE = {
  session_id: 5,
  recipe_id: 1,
  cooked_by: 'michael',
}

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<div>Home page</div>} />
        <Route path="/recipes/:id/cook" element={<div>Cooking mode page</div>} />
      </Routes>
      <CookingSessionRejoin />
    </MemoryRouter>
  )
}

describe('CookingSessionRejoin', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('does nothing when no user profile is set', async () => {
    api.getActiveSession.mockResolvedValue(ACTIVE)
    await act(async () => { renderAt('/') })

    expect(api.getActiveSession).not.toHaveBeenCalled()
    expect(screen.getByText('Home page')).toBeInTheDocument()
  })

  it('does nothing when there is no active session', async () => {
    setUser('michael')
    api.getActiveSession.mockResolvedValue(null)
    await act(async () => { renderAt('/') })

    expect(screen.getByText('Home page')).toBeInTheDocument()
  })

  it('does nothing when the active session belongs to the other user', async () => {
    setUser('rachel')
    api.getActiveSession.mockResolvedValue(ACTIVE)
    await act(async () => { renderAt('/') })

    expect(screen.getByText('Home page')).toBeInTheDocument()
  })

  it('navigates to the cook page when my own session is active', async () => {
    setUser('michael')
    api.getActiveSession.mockResolvedValue(ACTIVE)
    await act(async () => { renderAt('/') })

    expect(await screen.findByText('Cooking mode page')).toBeInTheDocument()
  })

  it('does not redirect if already on the matching cook page', async () => {
    setUser('michael')
    api.getActiveSession.mockResolvedValue(ACTIVE)
    await act(async () => { renderAt('/recipes/1/cook') })

    expect(screen.getByText('Cooking mode page')).toBeInTheDocument()
  })

  it('does not redirect away from a different (paired sibling) cook page either', async () => {
    // ACTIVE reports recipe 1 as the most-recently-active session, but we're
    // already on recipe 2's cook page (its paired sibling) — CookingMode's
    // own logic owns this page, so rejoin must not yank us to recipe 1.
    setUser('michael')
    api.getActiveSession.mockResolvedValue(ACTIVE)
    await act(async () => { renderAt('/recipes/2/cook?session=6') })

    expect(screen.getByText('Cooking mode page')).toBeInTheDocument()
    expect(api.getActiveSession).toHaveBeenCalled()
  })
})
