import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ReviewGate } from './ReviewGate'
import { api } from '../lib/api'
import { setUser } from '../lib/user'

vi.mock('../lib/api', () => ({
  api: {
    getPendingReviews: vi.fn(),
    rateSession: vi.fn(),
  },
}))

describe('ReviewGate', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('renders nothing when no user identity is set', async () => {
    const { container } = render(<ReviewGate />)
    await waitFor(() => expect(container).toBeEmptyDOMElement())
    expect(api.getPendingReviews).not.toHaveBeenCalled()
  })

  it('renders nothing when there are no pending reviews', async () => {
    setUser('rachel')
    api.getPendingReviews.mockResolvedValue([])

    const { container } = render(<ReviewGate />)
    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })

  it('blocks with a modal showing the oldest pending session first', async () => {
    setUser('rachel')
    api.getPendingReviews.mockResolvedValue([
      { id: 1, recipe_id: 10, recipe_name: 'Pasta', cooked_at: '2026-01-01T10:00:00' },
      { id: 2, recipe_id: 11, recipe_name: 'Curry', cooked_at: '2026-01-02T10:00:00' },
    ])

    render(<ReviewGate />)

    expect(await screen.findByText('Pasta')).toBeInTheDocument()
  })

  it('disables the submit button until a star rating is chosen', async () => {
    setUser('rachel')
    api.getPendingReviews.mockResolvedValue([
      { id: 1, recipe_id: 10, recipe_name: 'Pasta', cooked_at: '2026-01-01T10:00:00' },
    ])

    render(<ReviewGate />)
    await screen.findByText('Pasta')

    const submitButton = screen.getByRole('button', { name: /Opslaan/ })
    expect(submitButton).toBeDisabled()
  })

  it('rates the current session and advances the queue on submit', async () => {
    const user = userEvent.setup()
    setUser('rachel')
    api.getPendingReviews.mockResolvedValue([
      { id: 1, recipe_id: 10, recipe_name: 'Pasta', cooked_at: '2026-01-01T10:00:00' },
      { id: 2, recipe_id: 11, recipe_name: 'Curry', cooked_at: '2026-01-02T10:00:00' },
    ])
    api.rateSession.mockResolvedValue({})

    render(<ReviewGate />)
    await screen.findByText('Pasta')

    const stars = screen.getAllByRole('button', { name: '' }) // star buttons have no accessible name
    await user.click(stars[3]) // 4th star -> 4 stars

    const submitButton = screen.getByRole('button', { name: /Opslaan/ })
    expect(submitButton).not.toBeDisabled()
    await user.click(submitButton)

    await waitFor(() => {
      expect(api.rateSession).toHaveBeenCalledWith(1, { user: 'rachel', stars: 4 })
    })
    expect(await screen.findByText('Curry')).toBeInTheDocument()
  })

  it('closes once the queue is fully rated', async () => {
    const user = userEvent.setup()
    setUser('rachel')
    api.getPendingReviews.mockResolvedValue([
      { id: 1, recipe_id: 10, recipe_name: 'Pasta', cooked_at: '2026-01-01T10:00:00' },
    ])
    api.rateSession.mockResolvedValue({})

    const { container } = render(<ReviewGate />)
    await screen.findByText('Pasta')

    const stars = screen.getAllByRole('button', { name: '' })
    await user.click(stars[4])
    await user.click(screen.getByRole('button', { name: /Opslaan/ }))

    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })
})
