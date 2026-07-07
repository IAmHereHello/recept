import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { Planner } from './Planner'
import { api } from '../lib/api'

// jsdom's `navigator.share`/`navigator.clipboard` are read-only getters on
// Navigator.prototype, so they can't be reassigned directly. Stub the whole
// global with a prototype-linked object so unrelated navigator behavior
// (e.g. userEvent's userAgent checks) still falls through to the real one.
function stubNavigator({ share, clipboard } = {}) {
  vi.stubGlobal('navigator', Object.create(navigator, {
    share: { value: share, configurable: true },
    clipboard: { value: clipboard, configurable: true },
  }))
}

vi.mock('../lib/api', () => ({
  api: {
    getWeek: vi.fn(),
    getRecipes: vi.fn(),
    suggestWeek: vi.fn(),
    setDay: vi.fn(),
    clearDay: vi.fn(),
    getGroceries: vi.fn(),
    addSideDish: vi.fn(),
    removeSideDish: vi.fn(),
  },
}))

const EMPTY_WEEK = { mon: null, tue: null, wed: null, thu: null, fri: null, sat: null, sun: null }

function renderPlanner() {
  return render(
    <MemoryRouter>
      <Planner />
    </MemoryRouter>
  )
}

describe('Planner grocery share button', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getWeek.mockResolvedValue(EMPTY_WEEK)
    api.getRecipes.mockResolvedValue([])
    api.getGroceries.mockResolvedValue({
      week_start: '2026-01-05',
      by_recipe: { Soup: [{ name: 'Tomato', amount: '2', unit: '' }] },
    })
    stubNavigator()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  async function openGroceryModal(user) {
    await screen.findByText('Maaltijdplanner')
    await user.click(screen.getByRole('button', { name: /Boodschappen/ }))
    await screen.findByText('Boodschappenlijst')
  }

  it('shows confirmation when navigator.share succeeds', async () => {
    const user = userEvent.setup()
    stubNavigator({ share: vi.fn().mockResolvedValue(undefined) })
    renderPlanner()
    await openGroceryModal(user)

    await user.click(screen.getByRole('button', { name: 'Deel' }))

    expect(await screen.findByText('Gedeeld')).toBeInTheDocument()
  })

  it('silently does nothing when the user cancels the native share sheet', async () => {
    const user = userEvent.setup()
    const err = new Error('cancelled')
    err.name = 'AbortError'
    stubNavigator({ share: vi.fn().mockRejectedValue(err) })
    renderPlanner()
    await openGroceryModal(user)

    await user.click(screen.getByRole('button', { name: 'Deel' }))

    await waitFor(() => expect(navigator.share).toHaveBeenCalled())
    expect(screen.queryByText('Delen mislukt')).not.toBeInTheDocument()
  })

  it('shows an error message when navigator.share fails for another reason', async () => {
    const user = userEvent.setup()
    stubNavigator({ share: vi.fn().mockRejectedValue(new Error('boom')) })
    renderPlanner()
    await openGroceryModal(user)

    await user.click(screen.getByRole('button', { name: 'Deel' }))

    expect(await screen.findByText('Delen mislukt')).toBeInTheDocument()
  })

  it('falls back to clipboard and confirms when navigator.share is unavailable', async () => {
    const user = userEvent.setup()
    const writeText = vi.fn().mockResolvedValue(undefined)
    stubNavigator({ clipboard: { writeText } })
    renderPlanner()
    await openGroceryModal(user)

    await user.click(screen.getByRole('button', { name: 'Deel' }))

    expect(await screen.findByText('Gekopieerd naar klembord')).toBeInTheDocument()
    expect(writeText).toHaveBeenCalled()
  })

  it('shows an unsupported message when neither API is available', async () => {
    const user = userEvent.setup()
    // userEvent.setup() attaches its own clipboard stub to `navigator` as a
    // side effect, so (re-)stub after it runs to make sure both APIs are
    // genuinely absent for this assertion.
    stubNavigator()
    renderPlanner()
    await openGroceryModal(user)

    await user.click(screen.getByRole('button', { name: 'Deel' }))

    expect(await screen.findByText('Delen niet ondersteund op dit apparaat')).toBeInTheDocument()
  })
})

describe('Planner past days', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Only fake Date — leave real timers so testing-library's polling
    // (findBy/waitFor) keeps working normally.
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-01-07T12:00:00')) // Wednesday of the 2026-01-05 week
    api.getWeek.mockResolvedValue({
      mon: { week_start: '2026-01-05', day: 'mon', recipe_id: 1, locked: false },
      tue: null,
      wed: { week_start: '2026-01-05', day: 'wed', recipe_id: 2, locked: false },
      thu: null, fri: null, sat: null, sun: null,
    })
    api.getRecipes.mockResolvedValue([
      { id: 1, name: 'Monday Dish' },
      { id: 2, name: 'Wednesday Dish' },
    ])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('dims a past day, hides its edit affordances, but keeps the recipe link', async () => {
    renderPlanner()
    const mondayName = await screen.findByText('Monday Dish')
    const mondayCard = mondayName.closest('.rounded-xl')

    expect(mondayCard.className).toMatch(/opacity-50/)
    expect(within(mondayCard).queryByRole('button')).not.toBeInTheDocument() // no lock/clear icons
    expect(mondayName.closest('a')).toHaveAttribute('href', '/recipes/1')
  })

  it('does not dim today or future days and keeps their edit affordances', async () => {
    renderPlanner()
    const wedName = await screen.findByText('Wednesday Dish')
    const wedCard = wedName.closest('.rounded-xl')

    expect(wedCard.className).not.toMatch(/opacity-50/)
    expect(within(wedCard).getAllByRole('button').length).toBeGreaterThan(0) // lock + clear icons
  })

  it('shows a static placeholder instead of "kies gerecht" for an empty past day', async () => {
    renderPlanner()
    await screen.findByText('Monday Dish')

    expect(screen.getByText('Geen gerecht')).toBeInTheDocument() // Tuesday, past, no recipe
  })
})

describe('Planner side dishes', () => {
  const RECIPES = [
    { id: 1, name: 'Main Course' },
    { id: 2, name: 'Focaccia', is_side_dish: true },
    { id: 3, name: 'Sourdough Bread', is_baking: true },
  ]

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-01-05T12:00:00')) // Monday of the displayed week: nothing is past
    api.getWeek.mockResolvedValue({
      mon: { week_start: '2026-01-05', day: 'mon', recipe_id: 1, locked: false, sides: [] },
      tue: null, wed: null, thu: null, fri: null, sat: null, sun: null,
    })
    api.getRecipes.mockResolvedValue(RECIPES)
    api.setDay.mockResolvedValue({})
    api.addSideDish.mockResolvedValue({})
    api.removeSideDish.mockResolvedValue(undefined)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function dayCard(labelText) {
    return screen.getByText(labelText).closest('.rounded-xl')
  }

  it('excludes side-dish and baking recipes from the main-dish picker', async () => {
    const user = userEvent.setup()
    renderPlanner()
    await screen.findByText('Main Course')

    await user.click(within(dayCard('Dinsdag')).getByText('+ Kies gerecht'))
    await screen.findByText('Kies gerecht — Dinsdag')

    expect(screen.queryByText('Focaccia')).not.toBeInTheDocument()
    expect(screen.queryByText('Sourdough Bread')).not.toBeInTheDocument()
  })

  it('restricts the side-dish picker to recipes flagged as a side dish', async () => {
    const user = userEvent.setup()
    renderPlanner()
    await screen.findByText('Main Course')

    await user.click(within(dayCard('Maandag')).getByText('+ Bijgerecht'))
    const heading = await screen.findByText('Kies bijgerecht — Maandag')
    const modal = heading.closest('.rounded-t-2xl')

    expect(within(modal).getByText('Focaccia')).toBeInTheDocument()
    expect(within(modal).queryByText('Main Course')).not.toBeInTheDocument()
    expect(within(modal).queryByText('Sourdough Bread')).not.toBeInTheDocument()
  })

  it('adds a side dish and renders it as a chip', async () => {
    const user = userEvent.setup()
    renderPlanner()
    await screen.findByText('Main Course')

    await user.click(within(dayCard('Maandag')).getByText('+ Bijgerecht'))
    await screen.findByText('Focaccia')
    await user.click(screen.getByText('Focaccia'))

    expect(api.addSideDish).toHaveBeenCalledWith('2026-01-05', 'mon', 2)
    expect(await screen.findByText('Focaccia')).toBeInTheDocument()
  })

  it('removes a side dish chip', async () => {
    api.getWeek.mockResolvedValue({
      mon: { week_start: '2026-01-05', day: 'mon', recipe_id: 1, locked: false, sides: [{ recipe_id: 2, recipe_name: 'Focaccia' }] },
      tue: null, wed: null, thu: null, fri: null, sat: null, sun: null,
    })
    const user = userEvent.setup()
    renderPlanner()
    const chipText = await screen.findByText('Focaccia')
    const chip = chipText.closest('span')

    await user.click(within(chip).getByRole('button'))

    expect(api.removeSideDish).toHaveBeenCalledWith('2026-01-05', 'mon', 2)
    await waitFor(() => expect(screen.queryByText('Focaccia')).not.toBeInTheDocument())
  })
})
