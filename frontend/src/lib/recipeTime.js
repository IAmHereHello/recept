// The best "how long does this take" for a recipe: the median of your actual
// finished cooks once the backend has enough of them (typical_cook_seconds),
// otherwise the time entered on the recipe. Measured estimates are rounded to
// 5 minutes — false precision helps nobody when planning a week of dinners.
export function recipeTimeEstimate(recipe) {
  if (recipe?.typical_cook_seconds != null) {
    return {
      minutes: Math.max(5, Math.round(recipe.typical_cook_seconds / 60 / 5) * 5),
      measured: true,
    }
  }
  if (recipe?.cook_time != null) {
    return { minutes: recipe.cook_time, measured: false }
  }
  return null
}
