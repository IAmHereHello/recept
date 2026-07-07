import { useRef, useState } from 'react'
import { api } from '../lib/api'
import { Camera, Loader2 } from 'lucide-react'

export function PhotoUploader({ sessionId, uploadedBy, onUploaded, className = '' }) {
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef()

  async function handleChange(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError('')
    try {
      await api.uploadPhoto(sessionId, file, uploadedBy)
      onUploaded?.()
    } catch (err) {
      setError(err.message || 'Foto uploaden mislukt')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  return (
    <div className={className}>
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-xs rounded-lg p-2 mb-3">{error}</div>
      )}
      <input ref={fileRef} type="file" accept="image/*" onChange={handleChange} className="hidden" />
      <button type="button" onClick={() => fileRef.current?.click()}
        disabled={uploading}
        className="flex items-center gap-1.5 border border-gray-300 px-3 py-2 rounded-lg text-sm text-gray-600 hover:bg-white transition disabled:opacity-50">
        {uploading ? <Loader2 size={14} className="animate-spin" /> : <Camera size={14} />}
        Foto
      </button>
    </div>
  )
}
