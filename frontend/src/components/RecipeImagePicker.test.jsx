import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RecipeImagePicker } from './RecipeImagePicker'
import { api } from '../lib/api'

vi.mock('../lib/api', () => ({
  api: { uploadRecipeImage: vi.fn(), recipeImageFromUrl: vi.fn() },
}))

describe('RecipeImagePicker', () => {
  beforeEach(() => vi.clearAllMocks())

  it('uploads a chosen file and reports the stored path', async () => {
    const user = userEvent.setup()
    api.uploadRecipeImage.mockResolvedValue({ image_path: '/uploads/x.png' })
    const onChange = vi.fn()
    const { container } = render(<RecipeImagePicker value={null} onChange={onChange} />)

    const file = new File(['bytes'], 'dish.png', { type: 'image/png' })
    // first hidden input is the plain upload (the second one carries `capture`)
    await user.upload(container.querySelector('input[type="file"]'), file)

    await waitFor(() => expect(api.uploadRecipeImage).toHaveBeenCalledWith(file))
    expect(onChange).toHaveBeenCalledWith('/uploads/x.png')
  })

  it('fetches an image from a pasted URL', async () => {
    const user = userEvent.setup()
    api.recipeImageFromUrl.mockResolvedValue({ image_path: '/uploads/y.jpg' })
    const onChange = vi.fn()
    render(<RecipeImagePicker value={null} onChange={onChange} />)

    await user.click(screen.getByRole('button', { name: /URL/ }))
    await user.type(screen.getByPlaceholderText('https://...'), 'https://img.example/y.jpg')
    await user.click(screen.getByRole('button', { name: 'Ophalen' }))

    await waitFor(() =>
      expect(api.recipeImageFromUrl).toHaveBeenCalledWith('https://img.example/y.jpg')
    )
    expect(onChange).toHaveBeenCalledWith('/uploads/y.jpg')
  })

  it('surfaces a fetch error and keeps the picker open', async () => {
    const user = userEvent.setup()
    api.recipeImageFromUrl.mockRejectedValue(new Error('Kon geen afbeelding ophalen van deze URL.'))
    render(<RecipeImagePicker value={null} onChange={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /URL/ }))
    await user.type(screen.getByPlaceholderText('https://...'), 'https://img.example/nope')
    await user.click(screen.getByRole('button', { name: 'Ophalen' }))

    expect(await screen.findByText('Kon geen afbeelding ophalen van deze URL.')).toBeInTheDocument()
  })

  it('shows a preview with a working remove button when a value is set', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<RecipeImagePicker value="/uploads/cover.jpg" onChange={onChange} />)

    expect(screen.getByRole('img')).toHaveAttribute('src', '/uploads/cover.jpg')
    await user.click(screen.getByRole('button', { name: 'Afbeelding verwijderen' }))
    expect(onChange).toHaveBeenCalledWith(null)
  })
})
