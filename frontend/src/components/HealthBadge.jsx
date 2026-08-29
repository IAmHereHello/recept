// Nutri-Score-style letter grade for a recipe's AI healthiness score.
// Grade is derived server-side from health_score (see backend app/health.py).
const GRADE_STYLE = {
  A: 'bg-green-600 text-white',
  B: 'bg-lime-500 text-white',
  C: 'bg-yellow-400 text-yellow-950',
  D: 'bg-orange-500 text-white',
  E: 'bg-red-600 text-white',
}

const SIZE = {
  sm: 'w-5 h-5 text-xs',
  md: 'w-6 h-6 text-sm',
  lg: 'w-8 h-8 text-base',
}

export function HealthBadge({ grade, size = 'sm', onClick, title }) {
  if (!grade || !GRADE_STYLE[grade]) return null
  const cls = `inline-flex items-center justify-center rounded-full font-bold shrink-0 ${GRADE_STYLE[grade]} ${SIZE[size] || SIZE.sm}`
  if (onClick) {
    return (
      <button type="button" onClick={onClick} title={title} className={`${cls} transition hover:opacity-80`}>
        {grade}
      </button>
    )
  }
  return <span className={cls} title={title}>{grade}</span>
}
