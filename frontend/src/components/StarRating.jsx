import { Star } from 'lucide-react'

export function StarRating({ value, onChange, size = 6, readonly = false }) {
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => !readonly && onChange?.(n)}
          className={readonly ? 'cursor-default' : 'cursor-pointer'}
          disabled={readonly}
        >
          <Star
            size={size * 4}
            className={n <= (value || 0) ? 'fill-amber-400 text-amber-400' : 'text-gray-300'}
          />
        </button>
      ))}
    </div>
  )
}
