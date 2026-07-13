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
    createFreezerItem: vi.fn(),
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

  it('shows a freezer step after rating a freezable recipe, prefilled from portions', async () => {
    const user = userEvent.setup()
    setUser('rachel')
    api.getPendingReviews.mockResolvedValue([
      { id: 1, recipe_id: 10, recipe_name: 'Chili', cooked_at: '2026-01-01T10:00:00', is_freezable: true, portions: 4 },
    ])
    api.rateSession.mockResolvedValue({})

    render(<ReviewGate />)
    await screen.findByText('Chili')

    const stars = screen.getAllByRole('button', { name: '' })
    await user.click(stars[3])
    await user.click(screen.getByRole('button', { name: /Opslaan/ }))

    expect(await screen.findByText('Vriezer')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Aantal porties')).toHaveValue(4)
    expect(api.rateSession).toHaveBeenCalledWith(1, { user: 'rachel', stars: 4 })
  })

  it('does not show a freezer step for a non-freezable recipe, advancing the queue directly', async () => {
    const user = userEvent.setup()
    setUser('rachel')
    api.getPendingReviews.mockResolvedValue([
      { id: 1, recipe_id: 10, recipe_name: 'Salade', cooked_at: '2026-01-01T10:00:00', is_freezable: false, portions: null },
    ])
    api.rateSession.mockResolvedValue({})

    const { container } = render(<ReviewGate />)
    await screen.findByText('Salade')

    const stars = screen.getAllByRole('button', { name: '' })
    await user.click(stars[3])
    await user.click(screen.getByRole('button', { name: /Opslaan/ }))

    await waitFor(() => expect(container).toBeEmptyDOMElement())
    expect(api.createFreezerItem).not.toHaveBeenCalled()
  })

  it('Overslaan skips the freezer step without creating a freezer item', async () => {
    const user = userEvent.setup()
    setUser('rachel')
    api.getPendingReviews.mockResolvedValue([
      { id: 1, recipe_id: 10, recipe_name: 'Chili', cooked_at: '2026-01-01T10:00:00', is_freezable: true, portions: null },
    ])
    api.rateSession.mockResolvedValue({})

    const { container } = render(<ReviewGate />)
    await screen.findByText('Chili')

    const stars = screen.getAllByRole('button', { name: '' })
    await user.click(stars[3])
    await user.click(screen.getByRole('button', { name: /Opslaan/ }))
    await screen.findByText('Vriezer')

    await user.click(screen.getByRole('button', { name: 'Overslaan' }))

    await waitFor(() => expect(container).toBeEmptyDOMElement())
    expect(api.createFreezerItem).not.toHaveBeenCalled()
  })

  it('Bewaren creates a freezer item linked to the recipe and session, then advances', async () => {
    const user = userEvent.setup()
    setUser('rachel')
    api.getPendingReviews.mockResolvedValue([
      { id: 1, recipe_id: 10, recipe_name: 'Chili', cooked_at: '2026-01-01T10:00:00', is_freezable: true, portions: null },
      { id: 2, recipe_id: 11, recipe_name: 'Curry', cooked_at: '2026-01-02T10:00:00', is_freezable: false },
    ])
    api.rateSession.mockResolvedValue({})
    api.createFreezerItem.mockResolvedValue({})

    render(<ReviewGate />)
    await screen.findByText('Chili')

    const stars = screen.getAllByRole('button', { name: '' })
    await user.click(stars[3])
    await user.click(screen.getByRole('button', { name: /Opslaan/ }))
    await screen.findByText('Vriezer')

    await user.type(screen.getByPlaceholderText('Aantal porties'), '3')
    await user.click(screen.getByRole('button', { name: /Bewaren/ }))

    await waitFor(() => {
      expect(api.createFreezerItem).toHaveBeenCalledWith(
        expect.objectContaining({ recipe_id: 10, cook_session_id: 1, portions_total: 3, added_by: 'rachel' })
      )
    })
    expect(await screen.findByText('Curry')).toBeInTheDocument()
  })
})
