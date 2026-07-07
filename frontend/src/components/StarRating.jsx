import { Star } from 'lucide-react'

function clampFill(n) {
  return Math.max(0, Math.min(1, n))
}

function StarIcon({ size, fill }) {
  if (fill >= 1) return <Star size={size} className="fill-amber-400 text-amber-400" />
  if (fill <= 0) return <Star size={size} className="text-gray-300" />
  return (
    <span className="relative inline-block" style={{ width: size, height: size }}>
      <Star size={size} className="absolute inset-0 text-gray-300" />
      <span className="absolute inset-0 overflow-hidden" style={{ width: '50%' }}>
        <Star size={size} className="fill-amber-400 text-amber-400" />
      </span>
    </span>
  )
}

export function StarRating({ value, onChange, size = 6, readonly = false }) {
  function handleClick(e, n) {
    if (readonly) return
    const rect = e.currentTarget.getBoundingClientRect()
    const isLeftHalf = rect.width > 0 && (e.clientX - rect.left) < rect.width / 2
    onChange?.(isLeftHalf ? n - 0.5 : n)
  }

  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          onClick={(e) => handleClick(e, n)}
          className={readonly ? 'cursor-default' : 'cursor-pointer'}
          disabled={readonly}
        >
          <StarIcon size={size * 4} fill={clampFill((value || 0) - (n - 1))} />
        </button>
      ))}
    </div>
  )
}
