import { useEffect, useState } from 'react'
import { getUser, setUser } from '../lib/user'
import { checkForUpdate } from '../lib/serviceWorker'
import { api } from '../lib/api'
import { RefreshCw, Loader2 } from 'lucide-react'

const users = [
  { id: 'michael', label: 'Michael', emoji: '👨‍🍳' },
  { id: 'rachel', label: 'Rachel', emoji: '👩‍🍳' },
]

export function Settings() {
  const [current, setCurrent] = useState(getUser())
  const [updateStatus, setUpdateStatus] = useState(null)
  const [backendVersion, setBackendVersion] = useState(null)

  useEffect(() => {
    api.getHealth().then(h => setBackendVersion(h.version)).catch(() => {})
  }, [])

  function pick(id) {
    setUser(id)
    setCurrent(id)
  }

  async function handleCheckForUpdate() {
    setUpdateStatus('checking')
    const ok = await checkForUpdate()
    setUpdateStatus(ok ? 'checked' : 'unavailable')
    api.getHealth().then(h => setBackendVersion(h.version)).catch(() => {})
  }

  return (
    <div className="p-6 max-w-lg mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-1">Instellingen</h1>
      <p className="text-gray-500 mb-8">Wie ben jij op dit apparaat?</p>

      <div className="space-y-3">
        {users.map(({ id, label, emoji }) => (
          <button
            key={id}
            onClick={() => pick(id)}
            className={`w-full flex items-center gap-4 p-4 rounded-xl border-2 text-left transition-all
              ${current === id
                ? 'border-green-500 bg-green-50'
                : 'border-gray-200 bg-white hover:border-gray-300'
              }`}
          >
            <span className="text-3xl">{emoji}</span>
            <div>
              <div className="font-semibold text-gray-900">{label}</div>
              {current === id && (
                <div className="text-sm text-green-600">Actief</div>
              )}
            </div>
            {current === id && (
              <div className="ml-auto w-5 h-5 rounded-full bg-green-500 flex items-center justify-center">
                <span className="text-white text-xs">✓</span>
              </div>
            )}
          </button>
        ))}
      </div>

      {!current && (
        <p className="mt-6 text-sm text-amber-600 bg-amber-50 rounded-lg p-3">
          Selecteer eerst wie je bent om recepten te beoordelen.
        </p>
      )}

      <div className="mt-8 pt-6 border-t border-gray-100">
        <h2 className="text-sm font-semibold text-gray-900 mb-2">App-versie</h2>
        <p className="text-sm text-gray-500 mb-1">Frontend: <span className="font-mono">{__APP_VERSION__}</span></p>
        <p className="text-sm text-gray-500 mb-3">Backend: <span className="font-mono">{backendVersion || '…'}</span></p>
        <button
          onClick={handleCheckForUpdate}
          disabled={updateStatus === 'checking'}
          className="flex items-center gap-1.5 border border-gray-300 px-3 py-2 rounded-lg text-sm text-gray-600 hover:bg-white transition disabled:opacity-50"
        >
          {updateStatus === 'checking'
            ? <Loader2 size={14} className="animate-spin" />
            : <RefreshCw size={14} />}
          Controleer op updates
        </button>
        {updateStatus === 'checked' && (
          <p className="text-xs text-gray-400 mt-2">
            Gecontroleerd. Als er een nieuwe versie is, herlaadt de app zo automatisch.
          </p>
        )}
        {updateStatus === 'unavailable' && (
          <p className="text-xs text-gray-400 mt-2">Kon niet controleren (geen service worker actief).</p>
        )}
      </div>
    </div>
  )
}
