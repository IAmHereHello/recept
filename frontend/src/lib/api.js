const BASE = '/api'

async function req(method, path, body, isFormData = false) {
  const opts = { method, headers: {} }
  if (body && !isFormData) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  } else if (isFormData) {
    opts.body = body
  }
  const res = await fetch(BASE + path, opts)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  // Recipes
  getRecipes: (params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null))
    return req('GET', `/recipes/${q.toString() ? '?' + q : ''}`)
  },
  getRecipe: (id) => req('GET', `/recipes/${id}`),
  createRecipe: (data) => req('POST', '/recipes/', data),
  updateRecipe: (id, data) => req('PUT', `/recipes/${id}`, data),
  deleteRecipe: (id) => req('DELETE', `/recipes/${id}`),

  // Cook sessions
  getSessions: (recipeId) => req('GET', `/sessions/recipe/${recipeId}`),
  createSession: (data) => req('POST', '/sessions/', data),
  rateSession: (sessionId, data) => req('POST', `/sessions/${sessionId}/rate`, data),
  getPendingReviews: (user) => req('GET', `/sessions/pending/${user}`),
  uploadPhoto: (sessionId, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return req('POST', `/sessions/${sessionId}/photo`, fd, true)
  },

  // Planner
  getWeek: (weekStart) => req('GET', `/plan/${weekStart}`),
  suggestWeek: (weekStart, vegetarianOnly = false) =>
    req('POST', `/plan/suggest/${weekStart}?vegetarian_only=${vegetarianOnly}`),
  setDay: (weekStart, day, data) => req('PUT', `/plan/${weekStart}/${day}`, data),
  clearDay: (weekStart, day) => req('DELETE', `/plan/${weekStart}/${day}`),
  getGroceries: (weekStart) => req('POST', '/plan/grocery', { week_start: weekStart }),

  // Import
  importUrl: (url) => req('POST', '/import/', { url }),
}
