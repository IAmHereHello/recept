import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { recipeTimeEstimate } from '../lib/recipeTime'
import { RecipePrintSheet } from '../components/RecipePrintSheet'

// Bare print version of a recipe. Not linked from the app: the Pi's headless
// Chromium renders this URL to a PDF for direct printing (backend/app/printing.py).
export function RecipePrint() {
  const { id } = useParams()
  const [recipe, setRecipe] = useState(null)

  useEffect(() => { api.getRecipe(id).then(setRecipe) }, [id])

  useEffect(() => {
    if (recipe) document.title = recipe.name
  }, [recipe])

  if (!recipe) return null
  return <RecipePrintSheet recipe={recipe} timeEst={recipeTimeEstimate(recipe)} />
}
