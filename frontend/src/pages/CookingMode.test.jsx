import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { CookingMode } from './CookingMode'
import { api } from '../lib/api'
import { setUser } from '../lib/user'

vi.mock('../lib/api', () => ({
  api: {
    getRecipe: vi.fn(),
    getSession: vi.fn(),
    advanceStep: vi.fn(),
    startTimer: vi.fn(),
    clearTimer: vi.fn(),
    finishCooking: vi.fn(),
    uploadPhoto: vi.fn(),
  },
}))

const RECIPE = {
  id: 1,
  name: 'Ovenschotel',
  steps: [
    { id: 1, description: 'Verwarm de oven voor.' },
    { id: 2, description: 'Bak 20 minuten in de oven.' },
  ],
}

const SESSION = { id: 5, current_step: 0, finished_at: null }

function stubWakeLock() {
  const release = vi.fn().mockResolvedValue(undefined)
  const request = vi.fn().mockResolvedValue({ release })
  vi.stubGlobal('navigator', Object.create(navigator, {
    wakeLock: { value: { request }, configurable: true },
  }))
  return { request, release }
}

function renderCookingMode() {
  return render(
    <MemoryRouter initialEntries={['/recipes/1/cook?session=5']}>
      <Routes>
        <Route path="/recipes/:id/cook" element={<CookingMode />} />
        <Route path="/recipes/:id" element={<div>Recipe detail page</div>} />
      </Routes>
    </MemoryRouter>
  )
}

describe('CookingMode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setUser('michael')
    api.getRecipe.mockResolvedValue(RECIPE)
    api.getSession.mockResolvedValue(SESSION)
    api.advanceStep.mockResolvedValue({})
    api.startTimer.mockResolvedValue({})
    api.clearTimer.mockResolvedValue(null)
    api.finishCooking.mockResolvedValue({})
  })

  it('renders the first step and requests a wake lock on mount', async () => {
    const { request } = stubWakeLock()
    renderCookingMode()

    await screen.findByText('Stap 1 van 2')
    expect(screen.getByText('Ovenschotel')).toBeInTheDocument()
    expect(screen.getByText('Verwarm de oven voor.')).toBeInTheDocument()
    await waitFor(() => expect(request).toHaveBeenCalledWith('screen'))

    vi.unstubAllGlobals()
  })

  it('releases the wake lock on unmount', async () => {
    const { release } = stubWakeLock()
    const { unmount } = renderCookingMode()
    await screen.findByText('Stap 1 van 2')

    unmount()
    expect(release).toHaveBeenCalled()

    vi.unstubAllGlobals()
  })

  it('only shows a timer suggestion when the step text mentions minutes', async () => {
    stubWakeLock()
    const user = userEvent.setup()
    renderCookingMode()
    await screen.findByText('Stap 1 van 2')

    expect(screen.queryByText(/Start timer/)).not.toBeInTheDocument()

    await user.click(screen.getByText('Volgende'))
    await screen.findByText('Stap 2 van 2')

    expect(screen.getByText('Start timer (20 min)')).toBeInTheDocument()

    vi.unstubAllGlobals()
  })

  it('advances to the next step and calls the API with the new index', async () => {
    stubWakeLock()
    const user = userEvent.setup()
    renderCookingMode()
    await screen.findByText('Stap 1 van 2')

    await user.click(screen.getByText('Volgende'))

    expect(api.advanceStep).toHaveBeenCalledWith(5, 1)
    await screen.findByText('Bak 20 minuten in de oven.')

    vi.unstubAllGlobals()
  })

  it('disables "Vorige" on the first step', async () => {
    stubWakeLock()
    renderCookingMode()
    await screen.findByText('Stap 1 van 2')

    expect(screen.getByText('Vorige').closest('button')).toBeDisabled()

    vi.unstubAllGlobals()
  })

  it('shows the finish phase after the last step and completes cooking', async () => {
    stubWakeLock()
    const user = userEvent.setup()
    renderCookingMode()
    await screen.findByText('Stap 1 van 2')

    await user.click(screen.getByText('Volgende'))
    await screen.findByText('Stap 2 van 2')
    await user.click(screen.getByText('Klaar met stappen'))

    await screen.findByText('Klaar met koken!')

    await user.click(screen.getByRole('button', { name: /Klaar/ }))

    expect(api.finishCooking).toHaveBeenCalledWith(5)
    expect(await screen.findByText('Recipe detail page')).toBeInTheDocument()

    vi.unstubAllGlobals()
  })

  it('redirects back to the recipe if the session is already finished', async () => {
    stubWakeLock()
    api.getSession.mockResolvedValue({ id: 5, current_step: 0, finished_at: '2026-01-01T00:00:00' })
    renderCookingMode()

    expect(await screen.findByText('Recipe detail page')).toBeInTheDocument()

    vi.unstubAllGlobals()
  })
})
