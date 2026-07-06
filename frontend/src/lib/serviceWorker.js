let registrationPromise = null

// Registers the SW once on load, then proactively checks for a new version
// instead of relying on the browser's own background check, which per spec
// is throttled to roughly once every 24 hours — explicit update() calls
// bypass that throttle entirely.
export function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return

  navigator.serviceWorker.addEventListener('controllerchange', () => {
    window.location.reload()
  })

  window.addEventListener('load', () => {
    registrationPromise = navigator.serviceWorker.register('/sw.js', { scope: '/' })
    registrationPromise.then(reg => {
      reg.update()
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') reg.update()
      })
    })
  })
}

export async function checkForUpdate() {
  if (!registrationPromise) return false
  const reg = await registrationPromise
  await reg.update()
  return true
}
