import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { api } from './api'

describe('api', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('sends JSON body with correct headers on create', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: 1, name: 'Soup' }),
    })

    const result = await api.createRecipe({ name: 'Soup' })

    expect(global.fetch).toHaveBeenCalledWith('/api/recipes/', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Soup' }),
    }))
    expect(result).toEqual({ id: 1, name: 'Soup' })
  })

  it('returns null for 204 No Content responses', async () => {
    global.fetch.mockResolvedValue({ ok: true, status: 204 })
    const result = await api.deleteRecipe(1)
    expect(result).toBeNull()
  })

  it('throws using the server-provided error detail on failure', async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'Recipe not found' }),
    })

    await expect(api.getRecipe(999)).rejects.toThrow('Recipe not found')
  })

  it('falls back to statusText when the error body is not JSON', async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      json: async () => { throw new Error('not json') },
    })

    await expect(api.getRecipe(1)).rejects.toThrow('Internal Server Error')
  })

  it('omits null/undefined filters when listing recipes', async () => {
    global.fetch.mockResolvedValue({ ok: true, status: 200, json: async () => [] })

    await api.getRecipes({ cuisine: 'Italian', vegetarian: null, vegan: undefined })

    expect(global.fetch).toHaveBeenCalledWith('/api/recipes/?cuisine=Italian', expect.any(Object))
  })

  it('sends FormData as-is for photo uploads without a Content-Type override', async () => {
    global.fetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({}) })
    const file = new File(['data'], 'dinner.jpg', { type: 'image/jpeg' })

    await api.uploadPhoto(5, file)

    const [, opts] = global.fetch.mock.calls[0]
    expect(opts.headers['Content-Type']).toBeUndefined()
    expect(opts.body).toBeInstanceOf(FormData)
  })
})
