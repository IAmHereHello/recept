let registrationPromise = null

// Registers the SW immediately (not deferred to window 'load' — React can
// render and become interactive, including the manual update-check button,
// well before 'load' fires, which was racing registrationPromise below).
// Then proactively checks for a new version instead of relying on the
// browser's own background check, which per spec is throttled to roughly
// once every 24 hours — explicit update() calls bypass that throttle.
export function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return

  navigator.serviceWorker.addEventListener('controllerchange', () => {
    window.location.reload()
  })

  registrationPromise = navigator.serviceWorker.register('/sw.js', { scope: '/' })
  registrationPromise.then(reg => {
    reg.update()
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') reg.update()
    })
  })
}

export async function checkForUpdate() {
  const reg = registrationPromise
    ? await registrationPromise
    : await navigator.serviceWorker.getRegistration('/')
  if (!reg) return false
  await reg.update()
  return true
}
