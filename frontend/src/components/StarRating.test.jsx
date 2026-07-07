import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { StarRating } from './StarRating'

describe('StarRating', () => {
  it('clicking a star with no layout info (e.g. in tests) registers a whole star', () => {
    const onChange = vi.fn()
    render(<StarRating value={0} onChange={onChange} />)
    const stars = screen.getAllByRole('button')
    fireEvent.click(stars[3]) // 4th star
    expect(onChange).toHaveBeenCalledWith(4)
  })

  it('clicking the left half of a star registers a half star', () => {
    const onChange = vi.fn()
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue(
      { left: 0, width: 40, right: 40, top: 0, bottom: 40, height: 40, x: 0, y: 0, toJSON() {} }
    )
    render(<StarRating value={0} onChange={onChange} />)
    const stars = screen.getAllByRole('button')
    fireEvent.click(stars[2], { clientX: 10 }) // left quarter of the 3rd star
    expect(onChange).toHaveBeenCalledWith(2.5)
    vi.restoreAllMocks()
  })

  it('clicking the right half of a star registers a whole star', () => {
    const onChange = vi.fn()
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue(
      { left: 0, width: 40, right: 40, top: 0, bottom: 40, height: 40, x: 0, y: 0, toJSON() {} }
    )
    render(<StarRating value={0} onChange={onChange} />)
    const stars = screen.getAllByRole('button')
    fireEvent.click(stars[2], { clientX: 30 }) // right quarter of the 3rd star
    expect(onChange).toHaveBeenCalledWith(3)
    vi.restoreAllMocks()
  })

  it('readonly mode does not call onChange and disables buttons', () => {
    const onChange = vi.fn()
    render(<StarRating value={3.5} onChange={onChange} readonly />)
    const stars = screen.getAllByRole('button')
    stars.forEach(s => expect(s).toBeDisabled())
    fireEvent.click(stars[0])
    expect(onChange).not.toHaveBeenCalled()
  })

  it('renders a half-filled star for a fractional value', () => {
    const { container } = render(<StarRating value={3.5} readonly />)
    // 3 full stars, 1 half (has a nested clipped overlay span), 1 empty
    const halfWrapper = container.querySelectorAll('button')[3].querySelector('span.overflow-hidden')
    expect(halfWrapper).not.toBeNull()
  })
})
