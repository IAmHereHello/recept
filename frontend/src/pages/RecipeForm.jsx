import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { Plus, Trash2, Loader2, Link as LinkIcon, X } from 'lucide-react'

const EMPTY = {
  name: '', description: '', cook_time: '', difficulty: '',
  cuisine_type: '', is_vegetarian: false, is_vegan: false,
  ingredients: [], steps: [],
}

export function RecipeForm() {
  const { id } = useParams()
  const isEdit = Boolean(id)
  const navigate = useNavigate()
  const [form, setForm] = useState(EMPTY)
  const [loading, setLoading] = useState(isEdit)
  const [saving, setSaving] = useState(false)
  const [importUrl, setImportUrl] = useState('')
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (isEdit) {
      api.getRecipe(id).then(r => {
        setForm({ ...r, cook_time: r.cook_time ?? '' })
        setLoading(false)
      })
    }
  }, [id])

  function set(key, val) {
    setForm(f => ({ ...f, [key]: val }))
  }

  function addIngredient() {
    setForm(f => ({
      ...f,
      ingredients: [...f.ingredients, { name: '', amount: '', unit: '', sort_order: f.ingredients.length }],
    }))
  }

  function updateIngredient(i, key, val) {
    setForm(f => {
      const next = [...f.ingredients]
      next[i] = { ...next[i], [key]: val }
      return { ...f, ingredients: next }
    })
  }

  function removeIngredient(i) {
    setForm(f => ({ ...f, ingredients: f.ingredients.filter((_, j) => j !== i) }))
  }

  function addStep() {
    setForm(f => ({
      ...f,
      steps: [...f.steps, { sort_order: f.steps.length + 1, description: '' }],
    }))
  }

  function updateStep(i, val) {
    setForm(f => {
      const next = [...f.steps]
      next[i] = { ...next[i], description: val }
      return { ...f, steps: next }
    })
  }

  function removeStep(i) {
    setForm(f => ({
      ...f,
      steps: f.steps.filter((_, j) => j !== i).map((s, j) => ({ ...s, sort_order: j + 1 })),
    }))
  }

  async function doImport() {
    if (!importUrl.trim()) return
    setImporting(true)
    setError('')
    try {
      const data = await api.importUrl(importUrl.trim())
      setForm(f => ({
        ...f,
        ...data,
        cook_time: data.cook_time ?? '',
        ingredients: (data.ingredients || []).map((ing, i) => ({ ...ing, sort_order: i })),
        steps: (data.steps || []).map((s, i) => ({ ...s, sort_order: i + 1 })),
      }))
      setImportUrl('')
    } catch (e) {
      setError(e.message)
    } finally {
      setImporting(false)
    }
  }

  async function submit(e) {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      const payload = {
        ...form,
        cook_time: form.cook_time ? Number(form.cook_time) : null,
        difficulty: form.difficulty || null,
        ingredients: form.ingredients.filter(i => i.name.trim()),
        steps: form.steps.filter(s => s.description.trim()),
      }
      if (isEdit) {
        await api.updateRecipe(id, payload)
        navigate(`/recipes/${id}`)
      } else {
        const created = await api.createRecipe(payload)
        navigate(`/recipes/${created.id}`)
      }
    } catch (e) {
      setError(e.message)
      setSaving(false)
    }
  }

  if (loading) return <div className="p-6 text-center text-gray-400">Laden...</div>

  return (
    <form onSubmit={submit} className="p-4 pb-28 max-w-lg mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mt-4 mb-6">
        {isEdit ? 'Recept bewerken' : 'Nieuw recept'}
      </h1>

      {!isEdit && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-6">
          <p className="text-sm font-medium text-blue-800 mb-2 flex items-center gap-2">
            <LinkIcon size={14} /> Importeer van website
          </p>
          <div className="flex gap-2">
            <input
              value={importUrl}
              onChange={e => setImportUrl(e.target.value)}
              placeholder="Plak een URL..."
              className="flex-1 text-sm border border-blue-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
            />
            <button
              type="button"
              onClick={doImport}
              disabled={importing || !importUrl.trim()}
              className="flex items-center gap-1.5 bg-blue-600 text-white px-3 py-2 rounded-lg text-sm font-medium disabled:opacity-50 hover:bg-blue-700 transition"
            >
              {importing ? <Loader2 size={14} className="animate-spin" /> : 'Import'}
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl p-3 mb-4">{error}</div>
      )}

      <section className="space-y-4 mb-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Naam *</label>
          <input required value={form.name} onChange={e => set('name', e.target.value)}
            className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500" />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Beschrijving</label>
          <textarea rows={2} value={form.description || ''} onChange={e => set('description', e.target.value)}
            className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 resize-none" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Bereidingstijd (min)</label>
            <input type="number" min="1" value={form.cook_time} onChange={e => set('cook_time', e.target.value)}
              className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Moeilijkheid</label>
            <select value={form.difficulty} onChange={e => set('difficulty', e.target.value)}
              className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 bg-white">
              <option value="">—</option>
              <option value="easy">Makkelijk</option>
              <option value="medium">Gemiddeld</option>
              <option value="hard">Moeilijk</option>
            </select>
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Keuken</label>
          <input value={form.cuisine_type || ''} onChange={e => set('cuisine_type', e.target.value)}
            placeholder="Italiaans, Aziatisch..."
            className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500" />
        </div>
        <div className="flex gap-6">
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" checked={form.is_vegetarian} onChange={e => set('is_vegetarian', e.target.checked)}
              className="w-4 h-4 rounded accent-green-600" />
            <span>Vegetarisch</span>
          </label>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" checked={form.is_vegan} onChange={e => {
              set('is_vegan', e.target.checked)
              if (e.target.checked) set('is_vegetarian', true)
            }} className="w-4 h-4 rounded accent-green-600" />
            <span>Vegan</span>
          </label>
        </div>
      </section>

      <section className="mb-6">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-gray-900">Ingrediënten</h2>
          <button type="button" onClick={addIngredient}
            className="flex items-center gap-1 text-sm text-green-600 hover:text-green-700 font-medium">
            <Plus size={14} /> Toevoegen
          </button>
        </div>
        <div className="space-y-2">
          {form.ingredients.map((ing, i) => (
            <div key={i} className="flex gap-2">
              <input value={ing.amount} onChange={e => updateIngredient(i, 'amount', e.target.value)}
                placeholder="Hoeveelheid"
                className="w-20 border border-gray-200 rounded-lg px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500" />
              <input value={ing.unit} onChange={e => updateIngredient(i, 'unit', e.target.value)}
                placeholder="Eenheid"
                className="w-16 border border-gray-200 rounded-lg px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500" />
              <input value={ing.name} onChange={e => updateIngredient(i, 'name', e.target.value)}
                placeholder="Ingredient"
                className="flex-1 border border-gray-200 rounded-lg px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500" />
              <button type="button" onClick={() => removeIngredient(i)}
                className="text-gray-400 hover:text-red-500 transition shrink-0">
                <X size={16} />
              </button>
            </div>
          ))}
        </div>
      </section>

      <section className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-gray-900">Bereiding</h2>
          <button type="button" onClick={addStep}
            className="flex items-center gap-1 text-sm text-green-600 hover:text-green-700 font-medium">
            <Plus size={14} /> Stap
          </button>
        </div>
        <div className="space-y-3">
          {form.steps.map((step, i) => (
            <div key={i} className="flex gap-3">
              <span className="shrink-0 w-6 h-6 rounded-full bg-green-100 text-green-700 text-xs font-bold flex items-center justify-center mt-2">
                {i + 1}
              </span>
              <textarea rows={2} value={step.description} onChange={e => updateStep(i, e.target.value)}
                placeholder={`Stap ${i + 1}...`}
                className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 resize-none" />
              <button type="button" onClick={() => removeStep(i)}
                className="text-gray-400 hover:text-red-500 transition shrink-0 mt-2">
                <X size={16} />
              </button>
            </div>
          ))}
        </div>
      </section>

      <div className="fixed bottom-16 left-0 right-0 bg-white border-t border-gray-100 px-4 py-3 max-w-lg mx-auto">
        <div className="flex gap-3">
          <button type="button" onClick={() => navigate(-1)}
            className="flex-1 py-2.5 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 transition">
            Annuleren
          </button>
          <button type="submit" disabled={saving}
            className="flex-1 py-2.5 bg-green-600 text-white rounded-xl text-sm font-medium hover:bg-green-700 disabled:opacity-60 transition flex items-center justify-center gap-2">
            {saving && <Loader2 size={14} className="animate-spin" />}
            {isEdit ? 'Opslaan' : 'Recept aanmaken'}
          </button>
        </div>
      </div>
    </form>
  )
}
