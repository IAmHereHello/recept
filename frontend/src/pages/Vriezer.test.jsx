import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { Vriezer } from './Vriezer'
import { api } from '../lib/api'
import { setUser } from '../lib/user'

vi.mock('../lib/api', () => ({
  api: {
    getFreezerItems: vi.fn(),
    getRecipes: vi.fn(),
    createFreezerItem: vi.fn(),
    consumeFreezerItem: vi.fn(),
    setFreezerItemExpiry: vi.fn(),
    deleteFreezerItem: vi.fn(),
  },
}))

function renderVriezer() {
  return render(
    <MemoryRouter>
      <Vriezer />
    </MemoryRouter>
  )
}

function todayISO() {
  return new Date().toISOString().split('T')[0]
}

function isoInDays(days) {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d.toISOString().split('T')[0]
}

describe('Vriezer', () => {
  beforeEach(() => {
    localStorage.clear()
    setUser('rachel')
    vi.clearAllMocks()
  })

  it('shows an empty state when there is nothing in the freezer', async () => {
    api.getFreezerItems.mockResolvedValue([])
    renderVriezer()
    expect(await screen.findByText('Niets in de vriezer')).toBeInTheDocument()
  })

  it('lists freezer items with portions and THT', async () => {
    api.getFreezerItems.mockResolvedValue([
      { id: 1, recipe_id: 10, recipe_name: 'Chili', portions_total: 4, portions_remaining: 2, frozen_at: todayISO(), expires_at: isoInDays(30) },
    ])
    renderVriezer()
    expect(await screen.findByText('Chili')).toBeInTheDocument()
    expect(screen.getByText('2/4 porties')).toBeInTheDocument()
  })

  it('marks an item overdue in red when expires_at is in the past', async () => {
    api.getFreezerItems.mockResolvedValue([
      { id: 1, recipe_id: 10, recipe_name: 'Oude Soep', portions_total: 2, portions_remaining: 2, frozen_at: isoInDays(-100), expires_at: isoInDays(-1) },
    ])
    renderVriezer()
    const pill = await screen.findByText(/THT/)
    expect(pill.className).toContain('bg-red-50')
  })

  it('marks an item amber when within 14 days of expiry', async () => {
    api.getFreezerItems.mockResolvedValue([
      { id: 1, recipe_id: 10, recipe_name: 'Bijna Op', portions_total: 2, portions_remaining: 2, frozen_at: todayISO(), expires_at: isoInDays(10) },
    ])
    renderVriezer()
    const pill = await screen.findByText(/THT/)
    expect(pill.className).toContain('bg-amber-50')
  })

  it('marks an item neutral gray when far from expiry', async () => {
    api.getFreezerItems.mockResolvedValue([
      { id: 1, recipe_id: 10, recipe_name: 'Vers Ingevroren', portions_total: 2, portions_remaining: 2, frozen_at: todayISO(), expires_at: isoInDays(60) },
    ])
    renderVriezer()
    const pill = await screen.findByText(/THT/)
    expect(pill.className).toContain('bg-gray-100')
  })

  it('consuming all remaining portions removes the item from the list', async () => {
    const user = userEvent.setup()
    api.getFreezerItems.mockResolvedValue([
      { id: 1, recipe_id: 10, recipe_name: 'Chili', portions_total: 2, portions_remaining: 2, frozen_at: todayISO(), expires_at: isoInDays(30) },
    ])
    api.consumeFreezerItem.mockResolvedValue(null)
    renderVriezer()
    await screen.findByText('Chili')

    await user.click(screen.getByText('Gebruikt...'))
    await user.click(screen.getByRole('button', { name: 'Bevestigen' }))

    await waitFor(() => {
      expect(api.consumeFreezerItem).toHaveBeenCalledWith(1, { portions: 2 })
    })
    await waitFor(() => expect(screen.queryByText('Chili')).not.toBeInTheDocument())
  })

  it('consuming partial portions updates the remaining count in place', async () => {
    const user = userEvent.setup()
    api.getFreezerItems.mockResolvedValue([
      { id: 1, recipe_id: 10, recipe_name: 'Chili', portions_total: 4, portions_remaining: 4, frozen_at: todayISO(), expires_at: isoInDays(30) },
    ])
    api.consumeFreezerItem.mockResolvedValue({
      id: 1, recipe_id: 10, recipe_name: 'Chili', portions_total: 4, portions_remaining: 2, frozen_at: todayISO(), expires_at: isoInDays(30),
    })
    renderVriezer()
    await screen.findByText('Chili')

    await user.click(screen.getByText('Gebruikt...'))
    const input = screen.getByRole('spinbutton')
    await user.clear(input)
    await user.type(input, '2')
    await user.click(screen.getByRole('button', { name: 'Bevestigen' }))

    expect(await screen.findByText('2/4 porties')).toBeInTheDocument()
  })

  it('deletes an item after confirmation', async () => {
    const user = userEvent.setup()
    window.confirm = vi.fn(() => true)
    api.getFreezerItems.mockResolvedValue([
      { id: 1, recipe_id: 10, recipe_name: 'Chili', portions_total: 2, portions_remaining: 2, frozen_at: todayISO(), expires_at: isoInDays(30) },
    ])
    api.deleteFreezerItem.mockResolvedValue(null)
    renderVriezer()
    await screen.findByText('Chili')

    // pencil (edit) and trash (delete) icon buttons have no accessible name; trash is the last one
    const iconButtons = screen.getAllByRole('button', { name: '' })
    await user.click(iconButtons[iconButtons.length - 1])

    await waitFor(() => expect(api.deleteFreezerItem).toHaveBeenCalledWith(1))
  })

  it('add flow: pick a freezable recipe, then create a freezer item with prefilled portions and THT', async () => {
    const user = userEvent.setup()
    api.getFreezerItems.mockResolvedValue([])
    api.getRecipes.mockResolvedValue([
      { id: 20, name: 'Soep', portions: 6, freezer_months: 2, cover_photo: null },
    ])
    api.createFreezerItem.mockResolvedValue({
      id: 5, recipe_id: 20, recipe_name: 'Soep', portions_total: 6, portions_remaining: 6, frozen_at: todayISO(), expires_at: isoInDays(60),
    })
    renderVriezer()
    await screen.findByText('Niets in de vriezer')

    await user.click(screen.getByRole('button', { name: /Voeg toe/ }))
    expect(api.getRecipes).toHaveBeenCalledWith({ freezable: true })

    await user.click(await screen.findByText('Soep'))

    await user.click(screen.getByRole('button', { name: 'Toevoegen' }))

    await waitFor(() => {
      expect(api.createFreezerItem).toHaveBeenCalledWith(
        expect.objectContaining({ recipe_id: 20, portions_total: 6, added_by: 'rachel' })
      )
    })
    expect(await screen.findByText('Soep')).toBeInTheDocument()
  })
})
