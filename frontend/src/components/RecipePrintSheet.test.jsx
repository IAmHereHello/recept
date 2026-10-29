import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { RecipePrintSheet } from './RecipePrintSheet'

const RECIPE = {
  id: 1, name: 'Pasta pesto', description: 'Snel en groen.', prep_time: 10, portions: 2,
  difficulty: 'easy', cuisine_type: 'Italiaans', is_vegetarian: true, is_vegan: false,
  cover_photo: null,
  ingredients: [
    { id: 1, name: 'pasta', amount: '250', unit: 'g' },
    { id: 2, name: 'basilicum', amount: null, unit: null },
  ],
  steps: [
    { sort_order: 0, description: 'Kook de pasta.', wait_time_minutes: 10, track: 'main' },
    { sort_order: 1, description: 'Meng met pesto.', track: 'main' },
    { sort_order: 2, description: 'Rooster pijnboompitten.', track: 'meanwhile' },
  ],
}

describe('RecipePrintSheet', () => {
  it('renders the recipe outside #root with meta, ingredients and numbered steps', () => {
    render(<RecipePrintSheet recipe={RECIPE} timeEst={{ minutes: 20, measured: false }} />)
    const sheet = screen.getByTestId('print-sheet')
    expect(sheet.parentElement).toBe(document.body)

    const s = within(sheet)
    expect(s.getByRole('heading', { level: 1, name: 'Pasta pesto' })).toBeInTheDocument()
    expect(s.getByText('20 min · 10 min actief · 2 porties · Makkelijk · Italiaans · Vegetarisch')).toBeInTheDocument()
    expect(s.getByText('250 g')).toBeInTheDocument()
    expect(s.getByText('basilicum')).toBeInTheDocument()
    expect(s.getByText('Kook de pasta.')).toBeInTheDocument()
    expect(s.getByText('(10 min wachten)', { exact: false })).toBeInTheDocument()
    expect(s.getByText('2')).toHaveClass('ps-num')
    expect(s.getByText('Rooster pijnboompitten.')).toBeInTheDocument()
  })
})
