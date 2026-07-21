import { Routes, Route } from 'react-router-dom'
import HRDashboard from './pages/HRDashboard'
import InterviewPage from './pages/InterviewPage'
import Toaster from './components/Toaster'
import './App.css'

function App() {
  return (
    <>
      <Toaster />
      <Routes>
        <Route path="/" element={<HRDashboard />} />
        <Route path="/interview/:token" element={<InterviewPage />} />
      </Routes>
    </>
  )
}

export default App
