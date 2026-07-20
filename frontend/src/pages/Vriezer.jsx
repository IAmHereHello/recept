import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { getUser } from '../lib/user'
import { Snowflake, X, ChefHat, Trash2, Pencil, Plus } from 'lucide-react'

const AMBER_THRESHOLD_DAYS = 14 // matches backend FREEZER_BOOST_WINDOW_DAYS

function daysUntil(isoDate) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const target = new Date(isoDate)
  return Math.round((target - today) / 86400000)
}

function thtPillClasses(isoDate) {
  const days = daysUntil(isoDate)
  if (days < 0) return 'bg-red-50 text-red-600'
  if (days <= AMBER_THRESHOLD_DAYS) return 'bg-amber-50 text-amber-600'
  return 'bg-gray-100 text-gray-600'
}

function addMonths(isoDate, months) {
  const d = new Date(isoDate)
  d.setMonth(d.getMonth() + months)
  return d.toISOString().split('T')[0]
}

function todayISO() {
  return new Date().toISOString().split('T')[0]
}

export function Vriezer() {
  const me = getUser()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [recipes, setRecipes] = useState([])
  const [addModal, setAddModal] = useState(null) // { step: 'pick' | 'form', recipe, search, portions, frozenAt, expiresAt }
  const [consumeTarget, setConsumeTarget] = useState(null) // { item, portions }
  const [editingExpiryId, setEditingExpiryId] = useState(null)

  useEffect(() => {
    load()
  }, [])

  function load() {
    setLoading(true)
    api.getFreezerItems().then(setItems).finally(() => setLoading(false))
  }

  function openAddModal() {
    api.getRecipes({ freezable: true }).then(setRecipes)
    setAddModal({ step: 'pick', recipe: null, search: '', portions: '', frozenAt: todayISO(), expiresAt: '' })
  }

  function pickRecipeForAdd(recipe) {
    const frozenAt = todayISO()
    setAddModal(a => ({
      ...a,
      step: 'form',
      recipe,
      portions: recipe.portions != null ? String(recipe.portions) : '',
      frozenAt,
      expiresAt: addMonths(frozenAt, recipe.freezer_months || 3),
    }))
  }

  async function submitAdd() {
    const portions = Number(addModal.portions)
    if (!portions || portions <= 0) return
    const created = await api.createFreezerItem({
      recipe_id: addModal.recipe.id,
      portions_total: portions,
      frozen_at: addModal.frozenAt,
      expires_at: addModal.expiresAt,
      added_by: me,
    })
    setItems(list => [...list, created].sort((a, b) => a.expires_at.localeCompare(b.expires_at)))
    setAddModal(null)
  }

  function openConsume(item) {
    setConsumeTarget({ item, portions: String(item.portions_remaining) })
  }

  async function submitConsume() {
    const portions = Number(consumeTarget.portions)
    if (!portions || portions <= 0) return
    const item = consumeTarget.item
    const updated = await api.consumeFreezerItem(item.id, { portions })
    if (updated) {
      setItems(list => list.map(i => (i.id === item.id ? updated : i)))
    } else {
      setItems(list => list.filter(i => i.id !== item.id))
    }
    setConsumeTarget(null)
  }

  async function updateExpiry(item, expiresAt) {
    const updated = await api.setFreezerItemExpiry(item.id, { expires_at: expiresAt })
    setItems(list => list.map(i => (i.id === item.id ? updated : i)).sort((a, b) => a.expires_at.localeCompare(b.expires_at)))
    setEditingExpiryId(null)
  }

  async function deleteItem(item) {
    if (!confirm(`"${item.recipe_name}" uit de vriezer verwijderen?`)) return
    await api.deleteFreezerItem(item.id)
    setItems(list => list.filter(i => i.id !== item.id))
  }

  const pickerRecipes = addModal
    ? recipes.filter(r => r.name.toLowerCase().includes(addModal.search.toLowerCase()))
    : []

  return (
    <div className="w-full p-4 pb-28 max-w-lg mx-auto">
      <div className="flex items-center justify-between mt-4 mb-6">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Snowflake size={22} className="text-sky-600" /> Vriezer
        </h1>
        <button
          onClick={openAddModal}
          className="flex items-center gap-1.5 bg-sky-600 text-white px-3 py-2 rounded-lg text-sm font-medium hover:bg-sky-700 transition"
        >
          <Plus size={14} /> Voeg toe
        </button>
      </div>

      {loading ? (
        <div className="text-center py-8 text-gray-400">Laden...</div>
      ) : items.length === 0 ? (
        <div className="text-center py-8 text-gray-400 text-sm italic">Niets in de vriezer</div>
      ) : (
        <div className="space-y-2">
          {items.map(item => (
            <div key={item.id} className="bg-white border border-gray-100 rounded-xl p-3 shadow-sm">
              <div className="flex items-center justify-between">
                <Link to={`/recipes/${item.recipe_id}`} className="text-sm font-medium text-gray-900 hover:text-sky-600">
                  {item.recipe_name}
                </Link>
                <div className="flex gap-1">
                  <button onClick={() => setEditingExpiryId(id => (id === item.id ? null : item.id))} className="p-1 text-gray-400 hover:text-gray-600">
                    <Pencil size={12} />
                  </button>
                  <button onClick={() => deleteItem(item)} className="p-1 text-gray-400 hover:text-red-500">
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
              <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                <span className="text-xs text-gray-500">{item.portions_remaining}/{item.portions_total} porties</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${thtPillClasses(item.expires_at)}`}>
                  THT {new Date(item.expires_at).toLocaleDateString('nl-NL', { day: 'numeric', month: 'short' })}
                </span>
                <button
                  onClick={() => openConsume(item)}
                  className="text-xs text-sky-600 hover:text-sky-700 font-medium ml-auto"
                >
                  Gebruikt...
                </button>
              </div>
              {editingExpiryId === item.id && (
                <input
                  type="date"
                  defaultValue={item.expires_at}
                  onChange={e => updateExpiry(item, e.target.value)}
                  className="mt-2 border border-gray-200 rounded-lg px-2 py-1.5 text-sm"
                  autoFocus
                />
              )}
            </div>
          ))}
        </div>
      )}

      {addModal && (
        <div className="fixed inset-0 bg-black/40 z-[60] flex items-end">
          <div className="bg-white w-full max-w-lg mx-auto rounded-t-2xl p-4 max-h-[70vh] flex flex-col">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-gray-900">
                {addModal.step === 'pick' ? 'Kies recept' : addModal.recipe.name}
              </h3>
              <button onClick={() => setAddModal(null)}><X size={20} className="text-gray-500" /></button>
            </div>

            {addModal.step === 'pick' ? (
              <>
                <input
                  value={addModal.search}
                  onChange={e => setAddModal(a => ({ ...a, search: e.target.value }))}
                  placeholder="Zoeken..."
                  className="border border-gray-200 rounded-lg px-3 py-2 text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-sky-500"
                  autoFocus
                />
                <div className="overflow-y-auto flex-1 space-y-2">
                  {pickerRecipes.map(r => (
                    <button
                      key={r.id}
                      onClick={() => pickRecipeForAdd(r)}
                      className="w-full flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 text-left"
                    >
                      {r.cover_photo
                        ? <img src={r.cover_photo} alt="" className="w-10 h-10 rounded-lg object-cover shrink-0" />
                        : <div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center shrink-0">
                            <ChefHat size={16} className="text-gray-300" />
                          </div>
                      }
                      <div className="text-sm font-medium text-gray-900">{r.name}</div>
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Aantal porties</label>
                  <input
                    type="number" min="1"
                    value={addModal.portions}
                    onChange={e => setAddModal(a => ({ ...a, portions: e.target.value }))}
                    className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Ingevroren op</label>
                    <input
                      type="date"
                      value={addModal.frozenAt}
                      onChange={e => setAddModal(a => ({ ...a, frozenAt: e.target.value }))}
                      className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">THT</label>
                    <input
                      type="date"
                      value={addModal.expiresAt}
                      onChange={e => setAddModal(a => ({ ...a, expiresAt: e.target.value }))}
                      className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                    />
                  </div>
                </div>
                <button
                  onClick={submitAdd}
                  disabled={!addModal.portions}
                  className="w-full bg-sky-600 text-white py-2.5 rounded-xl text-sm font-medium hover:bg-sky-700 disabled:opacity-50 transition"
                >
                  Toevoegen
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {consumeTarget && (
        <div className="fixed inset-0 bg-black/40 z-[60] flex items-end">
          <div className="bg-white w-full max-w-lg mx-auto rounded-t-2xl p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-gray-900">{consumeTarget.item.recipe_name} gebruikt</h3>
              <button onClick={() => setConsumeTarget(null)}><X size={20} className="text-gray-500" /></button>
            </div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Aantal porties</label>
            <input
              type="number" min="1" max={consumeTarget.item.portions_remaining}
              value={consumeTarget.portions}
              onChange={e => setConsumeTarget(c => ({ ...c, portions: e.target.value }))}
              className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-sky-500"
              autoFocus
            />
            <button
              onClick={submitConsume}
              disabled={!consumeTarget.portions}
              className="w-full bg-sky-600 text-white py-2.5 rounded-xl text-sm font-medium hover:bg-sky-700 disabled:opacity-50 transition"
            >
              Bevestigen
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
