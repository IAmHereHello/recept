import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { RecipeDetail } from './RecipeDetail'
import { api } from '../lib/api'
import { setUser } from '../lib/user'

vi.mock('../lib/api', () => ({
  api: {
    getRecipe: vi.fn(),
    getSessions: vi.fn(),
    createSession: vi.fn(),
    rateSession: vi.fn(),
    deleteRating: vi.fn(),
    uploadPhoto: vi.fn(),
    deletePhoto: vi.fn(),
    deleteRecipe: vi.fn(),
  },
}))

const RECIPE = {
  id: 1, name: 'Pasta', description: '', cook_time: 30, difficulty: 'easy',
  cuisine_type: '', is_vegetarian: false, is_vegan: false, avg_rating: 4,
  ingredients: [], steps: [], cover_photo: null,
}

const SESSION = {
  id: 5, recipe_id: 1, cooked_at: '2026-01-01T10:00:00', notes: null, cooked_by: 'michael',
  ratings: [
    { id: 1, user: 'michael', stars: 4 },
    { id: 2, user: 'rachel', stars: 3.5 },
  ],
  photos: [],
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={['/recipes/1']}>
      <Routes>
        <Route path="/recipes/:id" element={<RecipeDetail />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('RecipeDetail rating edit/delete', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    api.getRecipe.mockResolvedValue(RECIPE)
    api.getSessions.mockResolvedValue([SESSION])
  })

  it('shows edit/delete icons only for the current user\'s own rating', async () => {
    setUser('michael')
    renderDetail()
    await screen.findByText('Pasta')

    const michaelRow = screen.getByText('michael').closest('div')
    const rachelRow = screen.getByText('rachel').closest('div')

    expect(within(michaelRow).getAllByRole('button').length).toBeGreaterThan(5) // stars + pencil + trash
    // Rachel's row has only the readonly star buttons, no pencil/trash affordance
    expect(within(rachelRow).queryAllByRole('button').length).toBe(5)
  })

  it('edits own rating and saves the new value', async () => {
    const user = userEvent.setup()
    setUser('michael')
    api.rateSession.mockResolvedValue({})
    renderDetail()
    await screen.findByText('Pasta')

    const michaelRow = screen.getByText('michael').closest('div')
    const buttons = within(michaelRow).getAllByRole('button')
    const pencilButton = buttons[buttons.length - 2] // pencil precedes trash
    await user.click(pencilButton)

    await screen.findByText('Opslaan')
    await user.click(screen.getByText('Opslaan'))

    expect(api.rateSession).toHaveBeenCalledWith(5, { user: 'michael', stars: 4 })
  })

  it('cancels an in-progress edit without saving', async () => {
    const user = userEvent.setup()
    setUser('michael')
    renderDetail()
    await screen.findByText('Pasta')

    const michaelRow = screen.getByText('michael').closest('div')
    const buttons = within(michaelRow).getAllByRole('button')
    await user.click(buttons[buttons.length - 2])

    await screen.findByText('Annuleren')
    await user.click(screen.getByText('Annuleren'))

    expect(screen.queryByText('Annuleren')).not.toBeInTheDocument()
    expect(api.rateSession).not.toHaveBeenCalled()
  })

  it('deletes own rating after confirmation', async () => {
    const user = userEvent.setup()
    setUser('michael')
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    api.deleteRating.mockResolvedValue(undefined)
    renderDetail()
    await screen.findByText('Pasta')

    const michaelRow = screen.getByText('michael').closest('div')
    const buttons = within(michaelRow).getAllByRole('button')
    await user.click(buttons[buttons.length - 1]) // trash is last

    expect(api.deleteRating).toHaveBeenCalledWith(5, 'michael')
  })

  it('does not delete when the confirmation is declined', async () => {
    const user = userEvent.setup()
    setUser('michael')
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderDetail()
    await screen.findByText('Pasta')

    const michaelRow = screen.getByText('michael').closest('div')
    const buttons = within(michaelRow).getAllByRole('button')
    await user.click(buttons[buttons.length - 1])

    expect(api.deleteRating).not.toHaveBeenCalled()
  })
})

describe('RecipeDetail photo delete', () => {
  const SESSION_WITH_PHOTOS = {
    ...SESSION,
    photos: [
      { id: 10, file_path: '/uploads/mine.jpg', uploaded_by: 'michael' },
      { id: 11, file_path: '/uploads/theirs.jpg', uploaded_by: 'rachel' },
      { id: 12, file_path: '/uploads/unknown.jpg', uploaded_by: null },
    ],
  }

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    api.getRecipe.mockResolvedValue(RECIPE)
    api.getSessions.mockResolvedValue([SESSION_WITH_PHOTOS])
  })

  it('only shows a delete affordance on photos uploaded by the current user', async () => {
    setUser('michael')
    const { container } = renderDetail()
    await screen.findByText('Pasta')

    const images = [...container.querySelectorAll('img[src*="/uploads/"]')]
    const mineWrapper = images.find(img => img.src.includes('mine.jpg')).closest('div')
    const theirsWrapper = images.find(img => img.src.includes('theirs.jpg')).closest('div')
    const unknownWrapper = images.find(img => img.src.includes('unknown.jpg')).closest('div')

    expect(within(mineWrapper).getByRole('button')).toBeInTheDocument()
    expect(within(theirsWrapper).queryByRole('button')).not.toBeInTheDocument()
    expect(within(unknownWrapper).queryByRole('button')).not.toBeInTheDocument()
  })

  it('deletes an own photo after confirmation', async () => {
    const user = userEvent.setup()
    setUser('michael')
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    api.deletePhoto.mockResolvedValue(undefined)
    const { container } = renderDetail()
    await screen.findByText('Pasta')

    const images = [...container.querySelectorAll('img[src*="/uploads/"]')]
    const mineWrapper = images.find(img => img.src.includes('mine.jpg')).closest('div')
    await user.click(within(mineWrapper).getByRole('button'))

    expect(api.deletePhoto).toHaveBeenCalledWith(5, 10)
  })
})
