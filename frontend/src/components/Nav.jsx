import { NavLink } from 'react-router-dom'
import { BookOpen, Calendar, Settings, Home } from 'lucide-react'

const links = [
  { to: '/', icon: Home, label: 'Home' },
  { to: '/recipes', icon: BookOpen, label: 'Recepten' },
  { to: '/plan', icon: Calendar, label: 'Planner' },
  { to: '/settings', icon: Settings, label: 'Instellingen' },
]

export function Nav() {
  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 z-50 safe-bottom">
      <div className="flex justify-around max-w-lg mx-auto">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex flex-col items-center gap-0.5 px-4 py-3 text-xs font-medium transition-colors
               ${isActive ? 'text-green-600' : 'text-gray-500 hover:text-gray-700'}`
            }
          >
            <Icon size={22} />
            <span>{label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
