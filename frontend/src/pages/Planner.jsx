import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import {
  ChevronLeft, ChevronRight, Sparkles, Lock, Unlock, ShoppingCart, X, ChefHat, Snowflake
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

function dayISO(weekDate, day) {
  const d = new Date(weekDate)
  d.setDate(d.getDate() + DAYS.indexOf(day))
  return toISO(d)
}

export function Planner() {
  const [weekDate, setWeekDate] = useState(() => getMonday(new Date()))
  const weekStart = toISO(weekDate)
  const [plan, setPlan] = useState({})
  const [suggestions, setSuggestions] = useState(null)
  const [recipes, setRecipes] = useState([])
  const [picker, setPicker] = useState(null) // { day, mode: 'main' | 'side' }
  const [vegOnly, setVegOnly] = useState(false)
  const [loading, setLoading] = useState(true)
  const [grocery, setGrocery] = useState(null)
  const [search, setSearch] = useState('')
  const [shareStatus, setShareStatus] = useState('')
  const [freezerConsumeTarget, setFreezerConsumeTarget] = useState(null) // { day, item: entry.freezer, freezerItemId, portions }

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
    const s = suggestions?.[day]
    if (!s) return
    const freezerItemId = s.from_freezer ? s.freezer_item_id : null
    const entry = { week_start: weekStart, day, recipe_id: s.id, locked: false, freezer_item_id: freezerItemId }
    await api.setDay(weekStart, day, entry)
    if (freezerItemId) {
      // Suggestions only carry portions_remaining, not the full freezer batch
      // shape get_week() attaches (portions_total/expires_at) — refetch that
      // day's info from the source of truth rather than guessing it locally.
      const week = await api.getWeek(weekStart)
      setPlan(p => ({ ...p, [day]: week[day] }))
    } else {
      setPlan(p => ({ ...p, [day]: { ...entry, recipe: s, sides: p[day]?.sides || [] } }))
    }
  }

  async function applyAllSuggestions() {
    await Promise.all(DAYS.filter(day => suggestions?.[day]).map(day => applySuggestion(day)))
  }

  async function toggleLock(day) {
    const entry = plan[day]
    if (!entry?.recipe_id) return
    const updated = { week_start: weekStart, day, recipe_id: entry.recipe_id, locked: !entry.locked, freezer_item_id: entry.freezer_item_id ?? null }
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
    setPlan(p => ({ ...p, [day]: { ...entry, recipe_name: recipe.name, sides: p[day]?.sides || [] } }))
    setPicker(null)
  }

  async function addSide(day, recipe) {
    await api.addSideDish(weekStart, day, recipe.id)
    setPlan(p => ({
      ...p,
      [day]: {
        ...(p[day] || { week_start: weekStart, day, recipe_id: null, locked: false }),
        sides: [...(p[day]?.sides || []), { recipe_id: recipe.id, recipe_name: recipe.name }],
      },
    }))
    setPicker(null)
  }

  async function removeSide(day, recipeId) {
    await api.removeSideDish(weekStart, day, recipeId)
    setPlan(p => {
      const daySides = (p[day]?.sides || []).filter(s => s.recipe_id !== recipeId)
      if (!p[day]?.recipe_id && daySides.length === 0) {
        return { ...p, [day]: null }
      }
      return { ...p, [day]: { ...p[day], sides: daySides } }
    })
  }

  async function submitFreezerConsume() {
    const portions = Number(freezerConsumeTarget.portions)
    if (!portions || portions <= 0) return
    const { day, freezerItemId } = freezerConsumeTarget
    const updated = await api.consumeFreezerItem(freezerItemId, { portions })
    setPlan(p => ({
      ...p,
      [day]: updated
        ? { ...p[day], freezer: { portions_remaining: updated.portions_remaining, portions_total: updated.portions_total, expires_at: updated.expires_at } }
        : { ...p[day], freezer_item_id: null, freezer: null },
    }))
    setFreezerConsumeTarget(null)
  }

  function selectPickerRecipe(r) {
    if (picker.mode === 'side') return addSide(picker.day, r)
    return pickRecipe(picker.day, r)
  }

  async function loadGrocery() {
    const data = await api.getGroceries(weekStart)
    setGrocery(data)
  }

  async function shareGrocery() {
    const text = Object.entries(grocery.by_recipe)
      .map(([name, ings]) => `${name}:\n${ings.map(i => `  - ${i.amount || ''} ${i.unit || ''} ${i.name}`.trim()).join('\n')}`)
      .join('\n\n')
    try {
      if (navigator.share) {
        await navigator.share({ text })
        setShareStatus('Gedeeld')
      } else if (navigator.clipboard) {
        await navigator.clipboard.writeText(text)
        setShareStatus('Gekopieerd naar klembord')
      } else {
        setShareStatus('Delen niet ondersteund op dit apparaat')
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setShareStatus('Delen mislukt')
      }
    } finally {
      setTimeout(() => setShareStatus(''), 2500)
    }
  }

  function formatWeek() {
    const end = new Date(weekDate)
    end.setDate(end.getDate() + 6)
    return `${weekDate.toLocaleDateString('nl-NL', { day: 'numeric', month: 'short' })} – ${end.toLocaleDateString('nl-NL', { day: 'numeric', month: 'short' })}`
  }

  const pickerRecipes = recipes.filter(r =>
    r.name.toLowerCase().includes(search.toLowerCase()) &&
    (!vegOnly || r.is_vegetarian) &&
    (picker?.mode === 'side' ? r.is_side_dish : !r.is_side_dish && !r.is_baking)
  )

  return (
    <div className="w-full p-4 pb-28 max-w-lg mx-auto">
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
        <Link
          to="/vriezer"
          className="flex items-center gap-2 border border-gray-200 px-3 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition ml-auto"
        >
          <Snowflake size={14} /> Vriezer
        </Link>
        <button
          onClick={loadGrocery}
          className="flex items-center gap-2 border border-gray-200 px-3 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition"
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
            const isPast = dayISO(weekDate, day) < toISO(new Date())

            return (
              <div key={day} className={`bg-white border border-gray-100 rounded-xl p-3 shadow-sm ${isPast ? 'opacity-50' : ''}`}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{DAY_LABELS[day]}</span>
                  <div className="flex gap-1">
                    {recipeId && !isPast && (
                      <button onClick={() => toggleLock(day)} className="p-1 text-gray-400 hover:text-gray-600">
                        {entry?.locked ? <Lock size={12} /> : <Unlock size={12} />}
                      </button>
                    )}
                    {recipeId && !isPast && (
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
                    {Boolean(entry?.locked) && <Lock size={12} className="text-green-600" />}
                  </div>
                ) : isPast ? (
                  <div className="text-sm text-gray-300 italic">Geen gerecht</div>
                ) : (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => { setPicker({ day, mode: 'main' }); setSearch('') }}
                      className="text-sm text-gray-400 hover:text-green-600 transition"
                    >
                      + Kies gerecht
                    </button>
                    {suggestion && !entry?.locked && (
                      <button
                        onClick={() => applySuggestion(day)}
                        className={
                          suggestion.from_freezer
                            ? 'text-xs text-sky-600 bg-sky-50 px-2 py-0.5 rounded-full hover:bg-sky-100 transition'
                            : 'text-xs text-green-600 bg-green-50 px-2 py-0.5 rounded-full hover:bg-green-100 transition'
                        }
                      >
                        {suggestion.from_freezer ? '❄️' : '✨'} {suggestion.name}
                      </button>
                    )}
                  </div>
                )}

                {suggestion && recipeName && !isPast && (
                  <div className="text-xs text-gray-400 mt-1">Suggestie: {suggestion.name}</div>
                )}

                {entry?.freezer_item_id && entry?.freezer && (
                  <div className="flex items-center gap-2 mt-1.5">
                    <span className="flex items-center gap-1 text-xs text-sky-600 bg-sky-50 px-2 py-0.5 rounded-full">
                      <Snowflake size={10} /> Uit de vriezer
                    </span>
                    {!isPast && (
                      <button
                        onClick={() => setFreezerConsumeTarget({
                          day, freezerItemId: entry.freezer_item_id,
                          portions: String(entry.freezer.portions_remaining),
                        })}
                        className="text-xs text-sky-600 hover:text-sky-700 font-medium"
                      >
                        Gegeten
                      </button>
                    )}
                  </div>
                )}

                {(entry?.sides?.length > 0 || !isPast) && (
                  <div className="flex items-center gap-1.5 flex-wrap mt-2">
                    {entry?.sides?.map(side => (
                      <span key={side.recipe_id} className="flex items-center gap-1 text-xs text-gray-600 bg-gray-100 px-2 py-0.5 rounded-full">
                        {side.recipe_name}
                        {!isPast && (
                          <button onClick={() => removeSide(day, side.recipe_id)} className="text-gray-400 hover:text-red-500">
                            <X size={10} />
                          </button>
                        )}
                      </span>
                    ))}
                    {!isPast && (
                      <button
                        onClick={() => { setPicker({ day, mode: 'side' }); setSearch('') }}
                        className="text-xs text-gray-400 hover:text-green-600 transition"
                      >
                        + Bijgerecht
                      </button>
                    )}
                  </div>
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
              <h3 className="font-semibold text-gray-900">
                {picker.mode === 'side' ? 'Kies bijgerecht' : 'Kies gerecht'} — {DAY_LABELS[picker.day]}
              </h3>
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
                  onClick={() => selectPickerRecipe(r)}
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

      {freezerConsumeTarget && (
        <div className="fixed inset-0 bg-black/40 z-[60] flex items-end">
          <div className="bg-white w-full max-w-lg mx-auto rounded-t-2xl p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-gray-900">Uit de vriezer gegeten</h3>
              <button onClick={() => setFreezerConsumeTarget(null)}><X size={20} className="text-gray-500" /></button>
            </div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Aantal porties</label>
            <input
              type="number" min="1"
              value={freezerConsumeTarget.portions}
              onChange={e => setFreezerConsumeTarget(c => ({ ...c, portions: e.target.value }))}
              className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-sky-500"
              autoFocus
            />
            <button
              onClick={submitFreezerConsume}
              disabled={!freezerConsumeTarget.portions}
              className="w-full bg-sky-600 text-white py-2.5 rounded-xl text-sm font-medium hover:bg-sky-700 disabled:opacity-50 transition"
            >
              Bevestigen
            </button>
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
                  onClick={shareGrocery}
                  className="text-sm text-green-600 font-medium"
                >
                  Deel
                </button>
                <button onClick={() => setGrocery(null)}><X size={20} className="text-gray-500" /></button>
              </div>
            </div>
            {shareStatus && (
              <div className="bg-green-50 border border-green-200 text-green-700 text-xs rounded-lg p-2 mb-3">
                {shareStatus}
              </div>
            )}
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
