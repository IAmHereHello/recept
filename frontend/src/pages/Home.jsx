import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { getUser } from '../lib/user'
import { StarRating } from '../components/StarRating'
import { Badge } from '../components/Badge'
import { ChefHat, Plus, Calendar } from 'lucide-react'

export function Home() {
  const [recipes, setRecipes] = useState([])
  const user = getUser()

  useEffect(() => {
    api.getRecipes().then(setRecipes).catch(console.error)
  }, [])

  const recent = [...recipes]
    .sort((a, b) => (b.last_cooked || '').localeCompare(a.last_cooked || ''))
    .slice(0, 5)

  const topRated = [...recipes]
    .filter(r => r.avg_rating)
    .sort((a, b) => b.avg_rating - a.avg_rating)
    .slice(0, 5)

  return (
    <div className="p-4 pb-24 max-w-lg mx-auto">
      <div className="flex items-center justify-between mb-6 mt-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <ChefHat size={28} className="text-green-600" />
            ReceptApp
          </h1>
          {user && (
            <p className="text-gray-500 text-sm capitalize">Hallo, {user}!</p>
          )}
        </div>
        <Link
          to="/recipes/new"
          className="flex items-center gap-1.5 bg-green-600 text-white px-3 py-2 rounded-lg text-sm font-medium hover:bg-green-700 transition"
        >
          <Plus size={16} /> Recept
        </Link>
      </div>

      {!user && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-6 text-sm text-amber-800">
          Ga naar <Link to="/settings" className="font-semibold underline">Instellingen</Link> om jezelf in te stellen.
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 mb-8">
        <Link to="/recipes" className="bg-white rounded-xl p-4 border border-gray-100 shadow-sm hover:shadow-md transition">
          <div className="text-2xl font-bold text-green-600">{recipes.length}</div>
          <div className="text-sm text-gray-500">Recepten</div>
        </Link>
        <Link to="/plan" className="bg-white rounded-xl p-4 border border-gray-100 shadow-sm hover:shadow-md transition flex items-center gap-2">
          <Calendar size={20} className="text-green-600" />
          <div className="text-sm font-medium text-gray-700">Maaltijdplanner</div>
        </Link>
      </div>

      {recent.length > 0 && (
        <section className="mb-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Recent gekookt</h2>
          <div className="space-y-2">
            {recent.map(r => <RecipeCard key={r.id} recipe={r} />)}
          </div>
        </section>
      )}

      {topRated.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Best beoordeeld</h2>
          <div className="space-y-2">
            {topRated.map(r => <RecipeCard key={r.id} recipe={r} />)}
          </div>
        </section>
      )}

      {recipes.length === 0 && (
        <div className="text-center py-16 text-gray-400">
          <ChefHat size={48} className="mx-auto mb-3 opacity-30" />
          <p>Nog geen recepten. Voeg er een toe!</p>
        </div>
      )}
    </div>
  )
}

function RecipeCard({ recipe }) {
  return (
    <Link
      to={`/recipes/${recipe.id}`}
      className="flex items-center gap-3 bg-white rounded-xl p-3 border border-gray-100 shadow-sm hover:shadow-md transition"
    >
      {recipe.cover_photo ? (
        <img src={recipe.cover_photo} alt="" className="w-16 h-16 rounded-lg object-cover shrink-0" />
      ) : (
        <div className="w-16 h-16 rounded-lg bg-gray-100 flex items-center justify-center shrink-0">
          <ChefHat size={24} className="text-gray-300" />
        </div>
      )}
      <div className="flex-1 min-w-0">
        <div className="font-medium text-gray-900 truncate">{recipe.name}</div>
        <div className="flex items-center gap-2 mt-1">
          {recipe.avg_rating && <StarRating value={Math.round(recipe.avg_rating)} readonly size={4} />}
          <div className="flex gap-1">
            {recipe.is_vegan && <Badge color="emerald">Vegan</Badge>}
            {!recipe.is_vegan && recipe.is_vegetarian && <Badge color="green">Veggie</Badge>}
            {recipe.cuisine_type && <Badge>{recipe.cuisine_type}</Badge>}
          </div>
        </div>
      </div>
    </Link>
  )
}
