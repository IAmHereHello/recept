import { describe, it, expect } from 'vitest'
import { recipeTimeEstimate } from './recipeTime'

describe('recipeTimeEstimate', () => {
  it('prefers measured typical time, rounded to 5 minutes', () => {
    expect(recipeTimeEstimate({ cook_time: 45, typical_cook_seconds: 3120 }))
      .toEqual({ minutes: 50, measured: true })
    expect(recipeTimeEstimate({ cook_time: 45, typical_cook_seconds: 2500 }))
      .toEqual({ minutes: 40, measured: true }) // 41.6 -> 40
  })

  it('never rounds a measured estimate below 5 minutes', () => {
    expect(recipeTimeEstimate({ typical_cook_seconds: 90 }))
      .toEqual({ minutes: 5, measured: true })
  })

  it('falls back to the authored cook_time', () => {
    expect(recipeTimeEstimate({ cook_time: 45, typical_cook_seconds: null }))
      .toEqual({ minutes: 45, measured: false })
  })

  it('returns null when the recipe has no time at all', () => {
    expect(recipeTimeEstimate({ cook_time: null, typical_cook_seconds: null })).toBeNull()
    expect(recipeTimeEstimate({})).toBeNull()
    expect(recipeTimeEstimate(null)).toBeNull()
  })
})
