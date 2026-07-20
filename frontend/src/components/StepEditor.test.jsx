import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StepEditor, stepsFromApi, stepsToApi, newStep } from './StepEditor'

describe('stepsFromApi / stepsToApi', () => {
  it('defaults track to main and preserves order when converting from the API', () => {
    const apiSteps = [
      { sort_order: 2, description: 'Bak', wait_time_minutes: 20 },
      { sort_order: 1, description: 'Meng' },
    ]
    const editorSteps = stepsFromApi(apiSteps)
    expect(editorSteps.map(s => s.description)).toEqual(['Meng', 'Bak'])
    expect(editorSteps.every(s => s.track === 'main')).toBe(true)
    expect(editorSteps[1].wait_time_minutes).toBe(20)
  })

  it('keeps meanwhile-tracked steps separate and preserves relative order per track', () => {
    const apiSteps = [
      { sort_order: 1, description: 'Prep', track: 'main' },
      { sort_order: 1, description: 'Chop', track: 'meanwhile' },
      { sort_order: 2, description: 'Bake', track: 'main' },
    ]
    const editorSteps = stepsFromApi(apiSteps)
    expect(editorSteps.filter(s => s.track === 'main').map(s => s.description)).toEqual(['Prep', 'Bake'])
    expect(editorSteps.filter(s => s.track === 'meanwhile').map(s => s.description)).toEqual(['Chop'])
  })

  it('recomputes sort_order per track and drops empty-description steps', () => {
    const steps = [
      { _key: 'a', description: 'Prep', wait_time_minutes: '', track: 'main' },
      { _key: 'b', description: '  ', wait_time_minutes: '', track: 'main' },
      { _key: 'c', description: 'Chop', wait_time_minutes: '', track: 'meanwhile' },
      { _key: 'd', description: 'Bake', wait_time_minutes: '25', track: 'main' },
    ]
    const payload = stepsToApi(steps)
    expect(payload).toEqual([
      { sort_order: 1, description: 'Prep', wait_time_minutes: null, track: 'main' },
      { sort_order: 1, description: 'Chop', wait_time_minutes: null, track: 'meanwhile' },
      { sort_order: 2, description: 'Bake', wait_time_minutes: 25, track: 'main' },
    ])
  })
})

describe('StepEditor', () => {
  it('adds a new step to the main track', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<StepEditor steps={[]} onChange={onChange} />)

    await user.click(screen.getAllByText('Stap toevoegen')[0])

    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ description: '', track: 'main' })])
  })

  it('adds a new step to the meanwhile track', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<StepEditor steps={[]} onChange={onChange} />)

    await user.click(screen.getAllByText('Stap toevoegen')[1])

    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ description: '', track: 'meanwhile' })])
  })

  it('moves a step to the meanwhile track via the switch-track button', async () => {
    const user = userEvent.setup()
    const step = { ...newStep('main'), description: 'Chop veggies' }
    const onChange = vi.fn()
    render(<StepEditor steps={[step]} onChange={onChange} />)

    await user.click(screen.getByTitle('Verplaats naar Ondertussen'))

    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ track: 'meanwhile' })])
  })

  it('reorders steps within the same track via the down button', async () => {
    const user = userEvent.setup()
    const stepA = { ...newStep('main'), description: 'First' }
    const stepB = { ...newStep('main'), description: 'Second' }
    const onChange = vi.fn()
    render(<StepEditor steps={[stepA, stepB]} onChange={onChange} />)

    const firstCard = screen.getByDisplayValue('First').closest('[data-step-key]')
    await user.click(within(firstCard).getByLabelText('Omlaag'))

    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ description: 'Second' }),
      expect.objectContaining({ description: 'First' }),
    ])
  })

  it('does not move a step past the start/end of its track', async () => {
    const user = userEvent.setup()
    const stepA = { ...newStep('main'), description: 'Only one' }
    const onChange = vi.fn()
    render(<StepEditor steps={[stepA]} onChange={onChange} />)

    const card = screen.getByDisplayValue('Only one').closest('[data-step-key]')
    await user.click(within(card).getByLabelText('Omhoog'))
    await user.click(within(card).getByLabelText('Omlaag'))

    expect(onChange).not.toHaveBeenCalled()
  })

  it('removes a step', async () => {
    const user = userEvent.setup()
    const step = { ...newStep('main'), description: 'Remove me' }
    const onChange = vi.fn()
    render(<StepEditor steps={[step]} onChange={onChange} />)

    const card = screen.getByDisplayValue('Remove me').closest('[data-step-key]')
    await user.click(within(card).getByLabelText('Verwijder stap'))

    expect(onChange).toHaveBeenCalledWith([])
  })

  it('bulk-adds pasted steps to the main track', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<StepEditor steps={[]} onChange={onChange} />)

    await user.click(screen.getByText('Plak meerdere stappen'))
    await user.type(screen.getByPlaceholderText(/Verwarm de oven/), 'Stap een\n\nStap twee')
    await user.click(screen.getByText('Toevoegen aan hoofdstappen'))

    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ description: 'Stap een', track: 'main' }),
      expect.objectContaining({ description: 'Stap twee', track: 'main' }),
    ])
  })
})
