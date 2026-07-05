import { useState } from 'react'
import { getUser, setUser } from '../lib/user'
import { User } from 'lucide-react'

const users = [
  { id: 'michael', label: 'Michael', emoji: '👨‍🍳' },
  { id: 'rachel', label: 'Rachel', emoji: '👩‍🍳' },
]

export function Settings() {
  const [current, setCurrent] = useState(getUser())

  function pick(id) {
    setUser(id)
    setCurrent(id)
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
    </div>
  )
}
