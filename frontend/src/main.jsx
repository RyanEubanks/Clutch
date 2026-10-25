import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { RecordingProvider } from './Recording.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <RecordingProvider>
      <App />
    </RecordingProvider>
  </StrictMode>,
)
