import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { StarRating } from '../components/StarRating'
import { Badge } from '../components/Badge'
import { Plus, Search, ChefHat, Filter } from 'lucide-react'

const DIFFICULTIES = ['', 'easy', 'medium', 'hard']
const DIFF_LABELS = { easy: 'Makkelijk', medium: 'Gemiddeld', hard: 'Moeilijk' }

export function RecipeList() {
  const [recipes, setRecipes] = useState([])
  const [search, setSearch] = useState('')
  const [vegetarian, setVegetarian] = useState(null)
  const [difficulty, setDifficulty] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.getRecipes({ vegetarian, difficulty: difficulty || undefined })
      .then(setRecipes)
      .finally(() => setLoading(false))
  }, [vegetarian, difficulty])

  const filtered = recipes.filter(r =>
    r.name.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="p-4 pb-24 max-w-lg mx-auto">
      <div className="flex items-center justify-between mb-4 mt-4">
        <h1 className="text-2xl font-bold text-gray-900">Recepten</h1>
        <Link
          to="/recipes/new"
          className="flex items-center gap-1.5 bg-green-600 text-white px-3 py-2 rounded-lg text-sm font-medium hover:bg-green-700 transition"
        >
          <Plus size={16} /> Nieuw
        </Link>
      </div>

      <div className="relative mb-3">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Zoek recept..."
          className="w-full pl-9 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
        />
      </div>

      <div className="flex gap-2 mb-4 flex-wrap">
        <button
          onClick={() => setVegetarian(vegetarian === null ? true : null)}
          className={`px-3 py-1.5 rounded-full text-sm font-medium border transition
            ${vegetarian ? 'bg-green-600 text-white border-green-600' : 'bg-white text-gray-600 border-gray-200'}`}
        >
          🌱 Vegetarisch
        </button>
        {DIFFICULTIES.filter(Boolean).map(d => (
          <button
            key={d}
            onClick={() => setDifficulty(difficulty === d ? '' : d)}
            className={`px-3 py-1.5 rounded-full text-sm font-medium border transition
              ${difficulty === d ? 'bg-green-600 text-white border-green-600' : 'bg-white text-gray-600 border-gray-200'}`}
          >
            {DIFF_LABELS[d]}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-center py-16 text-gray-400">Laden...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <ChefHat size={48} className="mx-auto mb-3 opacity-30" />
          <p>Geen recepten gevonden.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map(r => (
            <Link
              key={r.id}
              to={`/recipes/${r.id}`}
              className="flex gap-3 bg-white rounded-xl p-3 border border-gray-100 shadow-sm hover:shadow-md transition"
            >
              {r.cover_photo ? (
                <img src={r.cover_photo} alt="" className="w-20 h-20 rounded-lg object-cover shrink-0" />
              ) : (
                <div className="w-20 h-20 rounded-lg bg-gray-100 flex items-center justify-center shrink-0">
                  <ChefHat size={28} className="text-gray-300" />
                </div>
              )}
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-gray-900">{r.name}</div>
                {r.description && (
                  <div className="text-sm text-gray-500 truncate mt-0.5">{r.description}</div>
                )}
                <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                  {r.avg_rating && <StarRating value={Math.round(r.avg_rating)} readonly size={4} />}
                  {r.is_vegan && <Badge color="emerald">Vegan</Badge>}
                  {!r.is_vegan && r.is_vegetarian && <Badge color="green">Veggie</Badge>}
                  {r.cuisine_type && <Badge>{r.cuisine_type}</Badge>}
                  {r.difficulty && <Badge color="amber">{DIFF_LABELS[r.difficulty]}</Badge>}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
