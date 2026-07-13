import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { RecipeForm } from './RecipeForm'
import { api } from '../lib/api'

vi.mock('../lib/api', () => ({
  api: { createRecipe: vi.fn(), getRecipe: vi.fn(), updateRecipe: vi.fn() },
}))

function renderForm() {
  return render(
    <MemoryRouter>
      <RecipeForm />
    </MemoryRouter>
  )
}

// RecipeForm's <label> elements aren't associated to their inputs via
// for/id, so getByLabelText doesn't work here — same convention as other
// tests in this codebase (see PhotoUploader.test.jsx / RecipeDetail.test.jsx)
// of reaching into the DOM directly for unlabeled controls.
function inputNear(text) {
  return screen.getByText(text).closest('div').querySelector('input, select, textarea')
}

function checkboxNear(text) {
  return screen.getByText(text).closest('label').querySelector('input[type="checkbox"]')
}

describe('RecipeForm freezer fields', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.createRecipe.mockResolvedValue({ id: 1 })
  })

  it('defaults is_freezable to true and omits portions/freezer_months when left blank', async () => {
    const user = userEvent.setup()
    renderForm()

    await user.type(inputNear('Naam *'), 'Soep')
    await user.click(screen.getByRole('button', { name: /Recept aanmaken/ }))

    expect(api.createRecipe).toHaveBeenCalledWith(
      expect.objectContaining({ portions: null, is_freezable: true, freezer_months: null })
    )
  })

  it('coerces portions and freezer_months to numbers when filled in', async () => {
    const user = userEvent.setup()
    renderForm()

    await user.type(inputNear('Naam *'), 'Chili')
    await user.type(inputNear('Aantal porties'), '4')
    await user.type(inputNear('Vriezer THT (maanden)'), '2')
    await user.click(screen.getByRole('button', { name: /Recept aanmaken/ }))

    expect(api.createRecipe).toHaveBeenCalledWith(
      expect.objectContaining({ portions: 4, freezer_months: 2 })
    )
  })

  it('hides the freezer THT field once Invriesbaar is unchecked', async () => {
    const user = userEvent.setup()
    renderForm()

    expect(screen.getByText('Vriezer THT (maanden)')).toBeInTheDocument()
    await user.click(checkboxNear('Invriesbaar'))
    expect(screen.queryByText('Vriezer THT (maanden)')).not.toBeInTheDocument()
  })

  it('prefills freezer fields from an existing recipe when editing', async () => {
    api.getRecipe.mockResolvedValue({
      id: 5, name: 'Stoofpot', ingredients: [], steps: [],
      portions: 6, is_freezable: true, freezer_months: 4,
    })
    render(
      <MemoryRouter initialEntries={['/recipes/5/edit']}>
        <Routes>
          <Route path="/recipes/:id/edit" element={<RecipeForm />} />
        </Routes>
      </MemoryRouter>
    )

    expect(await screen.findByDisplayValue('Stoofpot')).toBeInTheDocument()
    expect(inputNear('Aantal porties')).toHaveValue(6)
    expect(inputNear('Vriezer THT (maanden)')).toHaveValue(4)
  })
})
