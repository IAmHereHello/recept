import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Nav } from './components/Nav'
import { ReviewGate } from './components/ReviewGate'
import { ActiveSessionBanner } from './components/ActiveSessionBanner'
import { CookingSessionRejoin } from './components/CookingSessionRejoin'
import { PersistentTimerBar } from './components/PersistentTimerBar'
import { Home } from './pages/Home'
import { RecipeList } from './pages/RecipeList'
import { RecipeDetail } from './pages/RecipeDetail'
import { RecipeForm } from './pages/RecipeForm'
import { CookingMode } from './pages/CookingMode'
import { Planner } from './pages/Planner'
import { Vriezer } from './pages/Vriezer'
import { Settings } from './pages/Settings'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/recipes" element={<RecipeList />} />
        <Route path="/recipes/new" element={<RecipeForm />} />
        <Route path="/recipes/:id" element={<RecipeDetail />} />
        <Route path="/recipes/:id/edit" element={<RecipeForm />} />
        <Route path="/recipes/:id/cook" element={<CookingMode />} />
        <Route path="/plan" element={<Planner />} />
        <Route path="/vriezer" element={<Vriezer />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
      <Nav />
      <ReviewGate />
      <ActiveSessionBanner />
      <CookingSessionRejoin />
      <PersistentTimerBar />
    </BrowserRouter>
  )
}
