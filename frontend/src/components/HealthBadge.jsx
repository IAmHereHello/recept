// Nutri-Score-style health grade. Grade is derived server-side from
// health_score (backend app/health.py). Colours are the official Nutri-Score
// palette; set via inline style since they're outside the Tailwind palette.
const GRADES = ['A', 'B', 'C', 'D', 'E']

const BG = { A: '#038141', B: '#85BB2F', C: '#FECB02', D: '#EE8100', E: '#E63E11' }
const FG = { A: '#ffffff', B: '#ffffff', C: '#1b1b00', D: '#ffffff', E: '#ffffff' }

const DIM = { sm: 18, md: 22, lg: 26 }

// Compact single-letter mark — recipe cards, planner suggestion chips.
export function HealthBadge({ grade, size = 'sm', onClick, title }) {
  if (!grade || !BG[grade]) return null
  const d = DIM[size] || DIM.sm
  const style = { backgroundColor: BG[grade], color: FG[grade], width: d, height: d, fontSize: Math.round(d * 0.6) }
  const cls = 'inline-flex items-center justify-center rounded-[4px] font-extrabold leading-none shrink-0'
  return onClick
    ? <button type="button" onClick={onClick} title={title} className={`${cls} transition hover:opacity-80`} style={style}>{grade}</button>
    : <span className={cls} style={style} title={title}>{grade}</span>
}

// Full A–E scale with the active grade enlarged — recipe detail panel.
export function HealthScale({ grade }) {
  return (
    <div
      className="inline-flex items-stretch rounded-md overflow-hidden select-none"
      role="img"
      aria-label={grade ? `Nutri-Score ${grade}` : 'Nutri-Score nog onbekend'}
    >
      {GRADES.map(g => {
        const active = g === grade
        return (
          <div
            key={g}
            className={`flex items-center justify-center font-extrabold transition-all ${active ? 'px-3 py-2 text-lg' : 'px-2 py-1.5 text-sm'}`}
            style={{
              backgroundColor: active ? BG[g] : '#e5e7eb',
              color: active ? FG[g] : '#9ca3af',
            }}
          >
            {g}
          </div>
        )
      })}
    </div>
  )
}
