import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import {
  ChevronLeft, ChevronRight, Sparkles, Lock, Unlock, ShoppingCart, X, ChefHat
} from 'lucide-react'

const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
const DAY_LABELS = { mon: 'Maandag', tue: 'Dinsdag', wed: 'Woensdag', thu: 'Donderdag', fri: 'Vrijdag', sat: 'Zaterdag', sun: 'Zondag' }

function getMonday(d) {
  const date = new Date(d)
  const day = date.getDay()
  const diff = date.getDate() - day + (day === 0 ? -6 : 1)
  date.setDate(diff)
  return date
}

function toISO(d) {
  return d.toISOString().split('T')[0]
}

function addWeeks(d, n) {
  const next = new Date(d)
  next.setDate(next.getDate() + n * 7)
  return next
}

export function Planner() {
  const [weekDate, setWeekDate] = useState(() => getMonday(new Date()))
  const weekStart = toISO(weekDate)
  const [plan, setPlan] = useState({})
  const [suggestions, setSuggestions] = useState(null)
  const [recipes, setRecipes] = useState([])
  const [picker, setPicker] = useState(null)
  const [vegOnly, setVegOnly] = useState(false)
  const [loading, setLoading] = useState(true)
  const [grocery, setGrocery] = useState(null)
  const [search, setSearch] = useState('')

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.getWeek(weekStart).then(setPlan),
      api.getRecipes().then(setRecipes),
    ]).finally(() => setLoading(false))
    setSuggestions(null)
  }, [weekStart])

  async function suggest() {
    const s = await api.suggestWeek(weekStart, vegOnly)
    setSuggestions(s)
  }

  async function applySuggestion(day) {
    if (!suggestions?.[day]) return
    const entry = { week_start: weekStart, day, recipe_id: suggestions[day].id, locked: false }
    await api.setDay(weekStart, day, entry)
    setPlan(p => ({ ...p, [day]: { ...entry, recipe: suggestions[day] } }))
  }

  async function applyAllSuggestions() {
    for (const day of DAYS) {
      if (suggestions?.[day]) await applySuggestion(day)
    }
  }

  async function toggleLock(day) {
    const entry = plan[day]
    if (!entry?.recipe_id) return
    const updated = { week_start: weekStart, day, recipe_id: entry.recipe_id, locked: !entry.locked }
    await api.setDay(weekStart, day, updated)
    setPlan(p => ({ ...p, [day]: { ...p[day], locked: !entry.locked } }))
  }

  async function clearDay(day) {
    await api.clearDay(weekStart, day)
    setPlan(p => ({ ...p, [day]: null }))
  }

  async function pickRecipe(day, recipe) {
    const entry = { week_start: weekStart, day, recipe_id: recipe.id, locked: false }
    await api.setDay(weekStart, day, entry)
    setPlan(p => ({ ...p, [day]: { ...entry, recipe_name: recipe.name } }))
    setPicker(null)
  }

  async function loadGrocery() {
    const data = await api.getGroceries(weekStart)
    setGrocery(data)
  }

  function formatWeek() {
    const end = new Date(weekDate)
    end.setDate(end.getDate() + 6)
    return `${weekDate.toLocaleDateString('nl-NL', { day: 'numeric', month: 'short' })} – ${end.toLocaleDateString('nl-NL', { day: 'numeric', month: 'short' })}`
  }

  const pickerRecipes = recipes.filter(r =>
    r.name.toLowerCase().includes(search.toLowerCase()) &&
    (!vegOnly || r.is_vegetarian)
  )

  return (
    <div className="p-4 pb-28 max-w-lg mx-auto">
      <div className="flex items-center justify-between mt-4 mb-4">
        <h1 className="text-2xl font-bold text-gray-900">Maaltijdplanner</h1>
      </div>

      <div className="flex items-center justify-between mb-4">
        <button onClick={() => setWeekDate(d => addWeeks(d, -1))} className="p-2 rounded-lg hover:bg-gray-100">
          <ChevronLeft size={20} />
        </button>
        <span className="text-sm font-medium text-gray-700">{formatWeek()}</span>
        <button onClick={() => setWeekDate(d => addWeeks(d, 1))} className="p-2 rounded-lg hover:bg-gray-100">
          <ChevronRight size={20} />
        </button>
      </div>

      <div className="flex gap-2 mb-4 flex-wrap">
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={vegOnly} onChange={e => setVegOnly(e.target.checked)} className="accent-green-600" />
          Alleen vegetarisch
        </label>
      </div>

      <div className="flex gap-2 mb-6">
        <button
          onClick={suggest}
          className="flex items-center gap-2 bg-green-600 text-white px-3 py-2 rounded-lg text-sm font-medium hover:bg-green-700 transition"
        >
          <Sparkles size={14} /> Suggesties
        </button>
        {suggestions && (
          <button
            onClick={applyAllSuggestions}
            className="flex items-center gap-2 border border-green-600 text-green-700 px-3 py-2 rounded-lg text-sm font-medium hover:bg-green-50 transition"
          >
            Alles toepassen
          </button>
        )}
        <button
          onClick={loadGrocery}
          className="flex items-center gap-2 border border-gray-200 px-3 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition ml-auto"
        >
          <ShoppingCart size={14} /> Boodschappen
        </button>
      </div>

      {loading ? (
        <div className="text-center py-8 text-gray-400">Laden...</div>
      ) : (
        <div className="space-y-2">
          {DAYS.map(day => {
            const entry = plan[day]
            const suggestion = suggestions?.[day]
            const recipeId = entry?.recipe_id
            const recipeName = recipeId
              ? recipes.find(r => r.id === recipeId)?.name || entry?.recipe_name || '...'
              : null

            return (
              <div key={day} className="bg-white border border-gray-100 rounded-xl p-3 shadow-sm">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{DAY_LABELS[day]}</span>
                  <div className="flex gap-1">
                    {recipeId && (
                      <button onClick={() => toggleLock(day)} className="p-1 text-gray-400 hover:text-gray-600">
                        {entry?.locked ? <Lock size={12} /> : <Unlock size={12} />}
                      </button>
                    )}
                    {recipeId && (
                      <button onClick={() => clearDay(day)} className="p-1 text-gray-400 hover:text-red-500">
                        <X size={12} />
                      </button>
                    )}
                  </div>
                </div>

                {recipeName ? (
                  <div className="flex items-center gap-2">
                    <Link to={`/recipes/${recipeId}`} className="text-sm font-medium text-gray-900 hover:text-green-600 flex-1">
                      {recipeName}
                    </Link>
                    {entry?.locked && <Lock size={12} className="text-green-600" />}
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => { setPicker(day); setSearch('') }}
                      className="text-sm text-gray-400 hover:text-green-600 transition"
                    >
                      + Kies gerecht
                    </button>
                    {suggestion && !entry?.locked && (
                      <button
                        onClick={() => applySuggestion(day)}
                        className="text-xs text-green-600 bg-green-50 px-2 py-0.5 rounded-full hover:bg-green-100 transition"
                      >
                        ✨ {suggestion.name}
                      </button>
                    )}
                  </div>
                )}

                {suggestion && recipeName && (
                  <div className="text-xs text-gray-400 mt-1">Suggestie: {suggestion.name}</div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {picker && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-end">
          <div className="bg-white w-full max-w-lg mx-auto rounded-t-2xl p-4 max-h-[70vh] flex flex-col">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-gray-900">Kies gerecht — {DAY_LABELS[picker]}</h3>
              <button onClick={() => setPicker(null)}><X size={20} className="text-gray-500" /></button>
            </div>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Zoeken..."
              className="border border-gray-200 rounded-lg px-3 py-2 text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-green-500"
              autoFocus
            />
            <div className="overflow-y-auto flex-1 space-y-2">
              {pickerRecipes.map(r => (
                <button
                  key={r.id}
                  onClick={() => pickRecipe(picker, r)}
                  className="w-full flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 text-left"
                >
                  {r.cover_photo
                    ? <img src={r.cover_photo} alt="" className="w-10 h-10 rounded-lg object-cover shrink-0" />
                    : <div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center shrink-0">
                        <ChefHat size={16} className="text-gray-300" />
                      </div>
                  }
                  <div>
                    <div className="text-sm font-medium text-gray-900">{r.name}</div>
                    {r.avg_rating && <div className="text-xs text-amber-500">★ {r.avg_rating.toFixed(1)}</div>}
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {grocery && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-end">
          <div className="bg-white w-full max-w-lg mx-auto rounded-t-2xl p-4 max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-gray-900">Boodschappenlijst</h3>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    const text = Object.entries(grocery.by_recipe)
                      .map(([name, ings]) => `${name}:\n${ings.map(i => `  - ${i.amount || ''} ${i.unit || ''} ${i.name}`.trim()).join('\n')}`)
                      .join('\n\n')
                    navigator.share?.({ text }) ?? navigator.clipboard?.writeText(text)
                  }}
                  className="text-sm text-green-600 font-medium"
                >
                  Deel
                </button>
                <button onClick={() => setGrocery(null)}><X size={20} className="text-gray-500" /></button>
              </div>
            </div>
            <div className="overflow-y-auto flex-1">
              {Object.entries(grocery.by_recipe).map(([recipeName, ings]) => (
                <div key={recipeName} className="mb-4">
                  <h4 className="text-sm font-semibold text-gray-700 mb-2">{recipeName}</h4>
                  <ul className="space-y-1">
                    {ings.map((ing, i) => (
                      <li key={i} className="flex items-center gap-2 text-sm text-gray-600">
                        <span className="w-1.5 h-1.5 rounded-full bg-green-400 shrink-0" />
                        {ing.amount && <span className="font-medium">{ing.amount} {ing.unit}</span>}
                        <span>{ing.name}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
