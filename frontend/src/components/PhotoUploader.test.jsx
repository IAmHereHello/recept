import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PhotoUploader } from './PhotoUploader'
import { api } from '../lib/api'

vi.mock('../lib/api', () => ({
  api: { uploadPhoto: vi.fn() },
}))

describe('PhotoUploader', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('uploads the selected file with the given uploader and calls onUploaded', async () => {
    const user = userEvent.setup()
    api.uploadPhoto.mockResolvedValue({})
    const onUploaded = vi.fn()
    const { container } = render(<PhotoUploader sessionId={7} uploadedBy="rachel" onUploaded={onUploaded} />)

    const file = new File(['data'], 'dinner.jpg', { type: 'image/jpeg' })
    const input = container.querySelector('input[type="file"]')
    await user.upload(input, file)

    await waitFor(() => expect(api.uploadPhoto).toHaveBeenCalledWith(7, file, 'rachel'))
    await waitFor(() => expect(onUploaded).toHaveBeenCalled())
  })

  it('shows an error message when the upload fails', async () => {
    const user = userEvent.setup()
    api.uploadPhoto.mockRejectedValue(new Error('Unsupported file type'))
    const { container } = render(<PhotoUploader sessionId={7} uploadedBy="rachel" />)

    const file = new File(['data'], 'dinner.jpg', { type: 'image/jpeg' })
    const input = container.querySelector('input[type="file"]')
    await user.upload(input, file)

    expect(await screen.findByText('Unsupported file type')).toBeInTheDocument()
  })
})
