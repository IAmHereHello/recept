const KEY = 'receptapp_user'

export function getUser() {
  return localStorage.getItem(KEY) // 'michael' | 'rachel' | null
}

export function setUser(name) {
  localStorage.setItem(KEY, name)
}

export function getOtherUser() {
  const u = getUser()
  if (u === 'michael') return 'rachel'
  if (u === 'rachel') return 'michael'
  return null
}
