import { useRef, useState } from 'react'
import { api } from '../lib/api'
import { Upload, Camera, Link as LinkIcon, X, Loader2 } from 'lucide-react'

// Add / replace a recipe's cover image. `value` is the "/uploads/..." path
// (or null); `onChange` receives the new path or null. Uploads and URL fetches
// resolve to a stored path immediately — the same shape an imported image has —
// so RecipeForm just carries the string and persists it on save.
export function RecipeImagePicker({ value, onChange }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [urlMode, setUrlMode] = useState(false)
  const [url, setUrl] = useState('')
  const uploadRef = useRef()
  const cameraRef = useRef()

  async function run(fn, fallbackMsg) {
    setBusy(true)
    setError('')
    try {
      const { image_path } = await fn()
      onChange(image_path)
      setUrl('')
      setUrlMode(false)
    } catch (e) {
      setError(e.message || fallbackMsg)
    } finally {
      setBusy(false)
    }
  }

  function handleFile(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (file) run(() => api.uploadRecipeImage(file), 'Uploaden mislukt')
  }

  if (value) {
    return (
      <div className="relative">
        <img src={value} alt="Recept afbeelding" className="w-full h-40 object-cover rounded-xl border border-gray-200" />
        <button
          type="button"
          onClick={() => onChange(null)}
          aria-label="Afbeelding verwijderen"
          className="absolute top-2 right-2 bg-black/60 text-white rounded-full p-1.5 hover:bg-black/80 transition"
        >
          <X size={14} />
        </button>
      </div>
    )
  }

  return (
    <div>
      <input ref={uploadRef} type="file" accept="image/*" onChange={handleFile} className="hidden" />
      <input ref={cameraRef} type="file" accept="image/*" capture="environment" onChange={handleFile} className="hidden" />
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => uploadRef.current?.click()}
          disabled={busy}
          className="flex items-center gap-1.5 border border-gray-300 px-3 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition disabled:opacity-50"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} Upload
        </button>
        <button
          type="button"
          onClick={() => cameraRef.current?.click()}
          disabled={busy}
          className="flex items-center gap-1.5 border border-gray-300 px-3 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition disabled:opacity-50"
        >
          <Camera size={14} /> Foto
        </button>
        <button
          type="button"
          onClick={() => { setUrlMode(v => !v); setError('') }}
          disabled={busy}
          className={`flex items-center gap-1.5 border px-3 py-2 rounded-lg text-sm transition disabled:opacity-50
            ${urlMode ? 'border-green-500 text-green-700 bg-green-50' : 'border-gray-300 text-gray-600 hover:bg-gray-50'}`}
        >
          <LinkIcon size={14} /> URL
        </button>
      </div>

      {urlMode && (
        <div className="flex gap-2 mt-2">
          <input
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder="https://..."
            className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500"
          />
          <button
            type="button"
            onClick={() => run(() => api.recipeImageFromUrl(url.trim()), 'Ophalen mislukt')}
            disabled={busy || !url.trim()}
            className="bg-green-600 text-white px-3 py-2 rounded-lg text-sm font-medium disabled:opacity-50 hover:bg-green-700 transition"
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : 'Ophalen'}
          </button>
        </div>
      )}

      {error && <p className="text-xs text-red-600 mt-2">{error}</p>}
    </div>
  )
}
