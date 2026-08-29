import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { RecipeForm } from './RecipeForm'
import { api } from '../lib/api'

vi.mock('../lib/api', () => ({
  api: {
    createRecipe: vi.fn(), getRecipe: vi.fn(), updateRecipe: vi.fn(),
    healthReview: vi.fn(), importUrl: vi.fn(),
    uploadRecipeImage: vi.fn(), recipeImageFromUrl: vi.fn(),
  },
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
    api.healthReview.mockResolvedValue({ id: 1 })
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

  it('auto-runs a health review after creating a recipe', async () => {
    const user = userEvent.setup()
    renderForm()

    await user.type(inputNear('Naam *'), 'Soep')
    await user.click(screen.getByRole('button', { name: /Recept aanmaken/ }))

    expect(api.healthReview).toHaveBeenCalledWith(1)
  })

  it('does not block recipe creation when the health review fails', async () => {
    api.healthReview.mockRejectedValue(new Error('AI down'))
    const user = userEvent.setup()
    renderForm()

    await user.type(inputNear('Naam *'), 'Soep')
    await user.click(screen.getByRole('button', { name: /Recept aanmaken/ }))

    expect(api.createRecipe).toHaveBeenCalled()
    expect(screen.queryByText('AI down')).not.toBeInTheDocument()
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

describe('RecipeForm step editor integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.createRecipe.mockResolvedValue({ id: 1 })
    api.healthReview.mockResolvedValue({ id: 1 })
  })

  it('submits main and meanwhile steps with wait times and fresh per-track sort_order', async () => {
    const user = userEvent.setup()
    renderForm()

    await user.type(inputNear('Naam *'), 'Ovenschotel')

    const addButtons = screen.getAllByText('Stap toevoegen')
    await user.click(addButtons[0]) // main step
    await user.type(screen.getAllByPlaceholderText('Beschrijf deze stap...')[0], 'Bak in de oven')
    await user.type(screen.getByPlaceholderText('Wachttijd (min, optioneel)'), '45')

    await user.click(screen.getAllByText('Stap toevoegen').at(-1)) // meanwhile step
    await user.type(screen.getAllByPlaceholderText('Beschrijf deze stap...')[1], 'Snijd de groenten')

    await user.click(screen.getByRole('button', { name: /Recept aanmaken/ }))

    expect(api.createRecipe).toHaveBeenCalledWith(
      expect.objectContaining({
        steps: [
          { sort_order: 1, description: 'Bak in de oven', wait_time_minutes: 45, track: 'main' },
          { sort_order: 1, description: 'Snijd de groenten', wait_time_minutes: null, track: 'meanwhile' },
        ],
      })
    )
  })

  it('prefills the editor with both tracks from an existing recipe', async () => {
    api.getRecipe.mockResolvedValue({
      id: 5, name: 'Stoofpot', ingredients: [],
      steps: [
        { sort_order: 1, description: 'Snijd het vlees', track: 'main' },
        { sort_order: 1, description: 'Was de aardappelen', track: 'meanwhile' },
      ],
    })
    render(
      <MemoryRouter initialEntries={['/recipes/5/edit']}>
        <Routes>
          <Route path="/recipes/:id/edit" element={<RecipeForm />} />
        </Routes>
      </MemoryRouter>
    )

    expect(await screen.findByDisplayValue('Snijd het vlees')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Was de aardappelen')).toBeInTheDocument()
  })
})

describe('RecipeForm imported cover image', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.createRecipe.mockResolvedValue({ id: 1 })
    api.healthReview.mockResolvedValue({ id: 1 })
  })

  it('previews an imported image and submits its path', async () => {
    api.importUrl.mockResolvedValue({
      name: 'Griekse ovenschotel', ingredients: [], steps: [],
      image_path: '/uploads/abc.jpg',
    })
    const user = userEvent.setup()
    renderForm()

    await user.type(screen.getByPlaceholderText('Plak een URL...'), 'https://ah.nl/recept')
    await user.click(screen.getByRole('button', { name: 'Import' }))

    const preview = await screen.findByRole('img')
    expect(preview).toHaveAttribute('src', '/uploads/abc.jpg')

    await user.click(screen.getByRole('button', { name: /Recept aanmaken/ }))
    expect(api.createRecipe).toHaveBeenCalledWith(
      expect.objectContaining({ image_path: '/uploads/abc.jpg' })
    )
  })

  it('drops the image when the remove button is clicked', async () => {
    api.importUrl.mockResolvedValue({
      name: 'Griekse ovenschotel', ingredients: [], steps: [],
      image_path: '/uploads/abc.jpg',
    })
    const user = userEvent.setup()
    renderForm()

    await user.type(screen.getByPlaceholderText('Plak een URL...'), 'https://ah.nl/recept')
    await user.click(screen.getByRole('button', { name: 'Import' }))
    await screen.findByRole('img')

    await user.click(screen.getByRole('button', { name: 'Afbeelding verwijderen' }))
    expect(screen.queryByRole('img')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Recept aanmaken/ }))
    expect(api.createRecipe).toHaveBeenCalledWith(
      expect.objectContaining({ image_path: null })
    )
  })

  it('sends image_path: null when nothing was imported', async () => {
    const user = userEvent.setup()
    renderForm()

    await user.type(inputNear('Naam *'), 'Soep')
    await user.click(screen.getByRole('button', { name: /Recept aanmaken/ }))

    expect(api.createRecipe).toHaveBeenCalledWith(
      expect.objectContaining({ image_path: null })
    )
  })
})
