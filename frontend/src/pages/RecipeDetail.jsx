import { useEffect, useState, useRef, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { api } from '../lib/api'
import { getUser, getOtherUser } from '../lib/user'
import { StarRating } from '../components/StarRating'
import { Badge } from '../components/Badge'
import {
  Clock, ChefHat, Pencil, Trash2, Camera, Plus, Loader2, Star
} from 'lucide-react'

const DIFF_LABELS = { easy: 'Makkelijk', medium: 'Gemiddeld', hard: 'Moeilijk' }
const USER_LABELS = { michael: 'Michael', rachel: 'Rachel' }

export function RecipeDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [recipe, setRecipe] = useState(null)
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [ratingSession, setRatingSession] = useState(null)
  const [myStars, setMyStars] = useState(0)
  const [otherStars, setOtherStars] = useState(0)
  const [rateOther, setRateOther] = useState(false)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef()
  const me = getUser()
  const other = getOtherUser()

  const load = useCallback(() => Promise.all([
    api.getRecipe(id).then(setRecipe),
    api.getSessions(id).then(setSessions),
  ]).finally(() => setLoading(false)), [id])

  useEffect(() => { load() }, [load])

  async function startCookSession() {
    const session = await api.createSession({ recipe_id: Number(id) })
    setSessions(s => [session, ...s])
    setRatingSession(session)
    setMyStars(0)
    setOtherStars(0)
    setRateOther(false)
  }

  async function submitRatings() {
    if (!ratingSession) return
    setSaving(true)
    try {
      if (me && myStars > 0) {
        await api.rateSession(ratingSession.id, { user: me, stars: myStars })
      }
      if (rateOther && other && otherStars > 0) {
        await api.rateSession(ratingSession.id, { user: other, stars: otherStars })
      }
      setRatingSession(null)
      await load()
    } finally {
      setSaving(false)
    }
  }

  async function handlePhoto(e) {
    const file = e.target.files?.[0]
    if (!file || !ratingSession) return
    setUploading(true)
    try {
      await api.uploadPhoto(ratingSession.id, file)
      await load()
    } finally {
      setUploading(false)
    }
  }

  async function deleteRecipe() {
    if (!confirm(`"${recipe.name}" verwijderen?`)) return
    await api.deleteRecipe(id)
    navigate('/recipes')
  }

  if (loading) return <div className="p-6 text-center text-gray-400">Laden...</div>
  if (!recipe) return <div className="p-6 text-center text-gray-400">Niet gevonden.</div>

  const latestSession = sessions[0]

  return (
    <div className="pb-24 max-w-lg mx-auto">
      {recipe.cover_photo ? (
        <div className="relative h-56 bg-gray-100">
          <img src={recipe.cover_photo} alt={recipe.name} className="w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/50 to-transparent" />
        </div>
      ) : (
        <div className="h-32 bg-gradient-to-br from-green-50 to-emerald-100 flex items-center justify-center">
          <ChefHat size={48} className="text-green-300" />
        </div>
      )}

      <div className="p-4">
        <div className="flex items-start justify-between gap-3 mb-3">
          <h1 className="text-2xl font-bold text-gray-900">{recipe.name}</h1>
          <div className="flex gap-2 shrink-0">
            <Link to={`/recipes/${id}/edit`} className="p-2 rounded-lg bg-gray-100 hover:bg-gray-200 transition">
              <Pencil size={16} className="text-gray-600" />
            </Link>
            <button onClick={deleteRecipe} className="p-2 rounded-lg bg-gray-100 hover:bg-red-100 transition">
              <Trash2 size={16} className="text-gray-500 hover:text-red-500" />
            </button>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 mb-4">
          {recipe.is_vegan && <Badge color="emerald">Vegan</Badge>}
          {!recipe.is_vegan && recipe.is_vegetarian && <Badge color="green">Vegetarisch</Badge>}
          {recipe.cuisine_type && <Badge>{recipe.cuisine_type}</Badge>}
          {recipe.difficulty && <Badge color="amber">{DIFF_LABELS[recipe.difficulty]}</Badge>}
          {recipe.cook_time && (
            <Badge color="blue">
              <span className="flex items-center gap-1"><Clock size={10} /> {recipe.cook_time} min</span>
            </Badge>
          )}
        </div>

        {recipe.avg_rating && (
          <div className="flex items-center gap-2 mb-4">
            <StarRating value={Math.round(recipe.avg_rating)} readonly size={5} />
            <span className="text-sm text-gray-500">{recipe.avg_rating.toFixed(1)}</span>
          </div>
        )}

        {recipe.description && (
          <p className="text-gray-600 text-sm mb-6">{recipe.description}</p>
        )}

        {recipe.ingredients?.length > 0 && (
          <section className="mb-6">
            <h2 className="text-base font-semibold text-gray-900 mb-3">Ingrediënten</h2>
            <ul className="space-y-1.5">
              {recipe.ingredients.map(ing => (
                <li key={ing.id} className="flex items-center gap-2 text-sm">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-500 shrink-0" />
                  {ing.amount && <span className="font-medium text-gray-700">{ing.amount} {ing.unit}</span>}
                  <span className="text-gray-600">{ing.name}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {recipe.steps?.length > 0 && (
          <section className="mb-6">
            <h2 className="text-base font-semibold text-gray-900 mb-3">Bereiding</h2>
            <ol className="space-y-3">
              {recipe.steps.map((step, i) => (
                <li key={step.id} className="flex gap-3">
                  <span className="shrink-0 w-6 h-6 rounded-full bg-green-100 text-green-700 text-xs font-bold flex items-center justify-center mt-0.5">
                    {i + 1}
                  </span>
                  <span className="text-sm text-gray-700">{step.description}</span>
                </li>
              ))}
            </ol>
          </section>
        )}

        <div className="border-t border-gray-100 pt-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-gray-900">Kooksessies</h2>
            <button
              onClick={startCookSession}
              className="flex items-center gap-1.5 bg-green-600 text-white px-3 py-2 rounded-lg text-sm font-medium hover:bg-green-700 transition"
            >
              <Plus size={14} /> Gekookt!
            </button>
          </div>

          {ratingSession && (
            <div className="bg-green-50 border border-green-200 rounded-xl p-4 mb-4">
              <p className="text-sm font-semibold text-green-800 mb-3">Beoordeel deze sessie</p>

              {me && (
                <div className="mb-3">
                  <p className="text-xs text-gray-600 mb-1">{USER_LABELS[me]}</p>
                  <StarRating value={myStars} onChange={setMyStars} size={6} />
                </div>
              )}

              <label className="flex items-center gap-2 text-sm text-gray-600 mb-3 cursor-pointer">
                <input type="checkbox" checked={rateOther} onChange={e => setRateOther(e.target.checked)}
                  className="accent-green-600" />
                Ook beoordelen voor {other ? USER_LABELS[other] : 'ander persoon'}
              </label>

              {rateOther && other && (
                <div className="mb-3">
                  <p className="text-xs text-gray-600 mb-1">{USER_LABELS[other]}</p>
                  <StarRating value={otherStars} onChange={setOtherStars} size={6} />
                </div>
              )}

              <div className="flex gap-2 mt-3">
                <input ref={fileRef} type="file" accept="image/*" onChange={handlePhoto} className="hidden" />
                <button type="button" onClick={() => fileRef.current?.click()}
                  disabled={uploading}
                  className="flex items-center gap-1.5 border border-gray-300 px-3 py-2 rounded-lg text-sm text-gray-600 hover:bg-white transition disabled:opacity-50">
                  {uploading ? <Loader2 size={14} className="animate-spin" /> : <Camera size={14} />}
                  Foto
                </button>
                <button onClick={submitRatings} disabled={saving}
                  className="flex-1 bg-green-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-60 transition flex items-center justify-center gap-2">
                  {saving && <Loader2 size={14} className="animate-spin" />}
                  Opslaan
                </button>
              </div>
            </div>
          )}

          {sessions.map(s => (
            <div key={s.id} className="border border-gray-100 rounded-xl p-3 mb-3 bg-white">
              <div className="text-xs text-gray-400 mb-2">
                {new Date(s.cooked_at).toLocaleDateString('nl-NL', { day: 'numeric', month: 'long', year: 'numeric' })}
              </div>
              {s.ratings.map(r => (
                <div key={r.id} className="flex items-center gap-2 mb-1">
                  <span className="text-xs text-gray-500 w-14 capitalize">{r.user}</span>
                  <StarRating value={r.stars} readonly size={4} />
                </div>
              ))}
              {s.photos.length > 0 && (
                <div className="flex gap-2 mt-2 flex-wrap">
                  {s.photos.map((p, i) => (
                    <img key={i} src={p} alt="" className="h-16 w-16 rounded-lg object-cover" />
                  ))}
                </div>
              )}
              {s.notes && <p className="text-xs text-gray-500 mt-2">{s.notes}</p>}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
