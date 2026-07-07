import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { RecipeList } from './RecipeList'
import { api } from '../lib/api'

vi.mock('../lib/api', () => ({
  api: { getRecipes: vi.fn() },
}))

function renderList() {
  return render(
    <MemoryRouter>
      <RecipeList />
    </MemoryRouter>
  )
}

describe('RecipeList baking filter', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getRecipes.mockResolvedValue([])
  })

  it('requests recipes without a baking filter by default', async () => {
    renderList()
    await screen.findByText('Recepten')

    expect(api.getRecipes).toHaveBeenCalledWith({ vegetarian: null, baking: null, difficulty: undefined })
  })

  it('toggles the baking filter on and off', async () => {
    const user = userEvent.setup()
    renderList()
    await screen.findByText('Recepten')

    await user.click(screen.getByText('🍞 Bakken'))
    expect(api.getRecipes).toHaveBeenLastCalledWith({ vegetarian: null, baking: true, difficulty: undefined })

    await user.click(screen.getByText('🍞 Bakken'))
    expect(api.getRecipes).toHaveBeenLastCalledWith({ vegetarian: null, baking: null, difficulty: undefined })
  })
})
