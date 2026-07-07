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
  deleteRating: (sessionId, user) => req('DELETE', `/sessions/${sessionId}/rate/${user}`),
  getPendingReviews: (user) => req('GET', `/sessions/pending/${user}`),
  getSession: (sessionId) => req('GET', `/sessions/${sessionId}`),
  uploadPhoto: (sessionId, file, uploadedBy) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('uploaded_by', uploadedBy)
    return req('POST', `/sessions/${sessionId}/photo`, fd, true)
  },
  deletePhoto: (sessionId, photoId) => req('DELETE', `/sessions/${sessionId}/photo/${photoId}`),
  advanceStep: (sessionId, stepIndex) => req('POST', `/sessions/${sessionId}/step`, { step_index: stepIndex }),
  startTimer: (sessionId, seconds) => req('POST', `/sessions/${sessionId}/timer`, { seconds }),
  clearTimer: (sessionId) => req('DELETE', `/sessions/${sessionId}/timer`),
  finishCooking: (sessionId) => req('POST', `/sessions/${sessionId}/finish`),
  getActiveSession: () => req('GET', '/sessions/active'),

  // Planner
  getWeek: (weekStart) => req('GET', `/plan/${weekStart}`),
  suggestWeek: (weekStart, vegetarianOnly = false) =>
    req('POST', `/plan/suggest/${weekStart}?vegetarian_only=${vegetarianOnly}`),
  setDay: (weekStart, day, data) => req('PUT', `/plan/${weekStart}/${day}`, data),
  clearDay: (weekStart, day) => req('DELETE', `/plan/${weekStart}/${day}`),
  getGroceries: (weekStart) => req('POST', '/plan/grocery', { week_start: weekStart }),
  addSideDish: (weekStart, day, recipeId) => req('POST', `/plan/${weekStart}/${day}/sides`, { recipe_id: recipeId }),
  removeSideDish: (weekStart, day, recipeId) => req('DELETE', `/plan/${weekStart}/${day}/sides/${recipeId}`),

  // Import
  importUrl: (url) => req('POST', '/import/', { url }),

  // Health / version — served at /health directly, not under /api
  getHealth: () => fetch('/health').then(res => res.json()),
}
