import { createContext, useContext } from 'react'

// Lecture recording state, provided by RecordingProvider in Recording.jsx
export const RecordingContext = createContext(null)

export function useRecording() {
  return useContext(RecordingContext)
}
