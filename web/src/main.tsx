import '@fontsource-variable/bricolage-grotesque'
import '@fontsource-variable/instrument-sans'
import '@fontsource-variable/jetbrains-mono'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import './styles/base.css'
import { JobPage } from './pages/JobPage'
import { Landing } from './pages/Landing'
import { NotFound } from './pages/NotFound'
import { Start } from './pages/Start'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/app" element={<Start />} />
        <Route path="/app/jobs/:jobId" element={<JobPage />} />
        <Route path="/app/jobs/:jobId/:section" element={<JobPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
