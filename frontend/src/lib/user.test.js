import { describe, it, expect, beforeEach } from 'vitest'
import { getUser, setUser, getOtherUser } from './user'

describe('user', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('returns null when no user is set', () => {
    expect(getUser()).toBeNull()
    expect(getOtherUser()).toBeNull()
  })

  it('persists the chosen user in localStorage', () => {
    setUser('michael')
    expect(getUser()).toBe('michael')
  })

  it('getOtherUser returns the opposite of the current user', () => {
    setUser('michael')
    expect(getOtherUser()).toBe('rachel')

    setUser('rachel')
    expect(getOtherUser()).toBe('michael')
  })
})
