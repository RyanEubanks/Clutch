import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import { micErrorMessage, micProblem, startRecording } from './recorder'
import { RecordingContext } from './useRecording'

// Lecture recording lives above the pages, so it keeps going while you use other tabs.
// Each ~25 s piece is transcribed as soon as it's recorded; the transcript is backed up in
// this browser so a closed tab or crash doesn't lose a lecture.

const DRAFT_KEY = 'clutch.lectureDraft'

function loadDraft() {
  try {
    return JSON.parse(localStorage.getItem(DRAFT_KEY))
  } catch {
    return null
  }
}

function saveDraft(draft) {
  try {
    if (draft) localStorage.setItem(DRAFT_KEY, JSON.stringify(draft))
    else localStorage.removeItem(DRAFT_KEY)
  } catch {
    // Storage unavailable: the transcript just isn't backed up
  }
}

export function RecordingProvider({ children }) {
  // idle → recording ⇄ paused → finishing (last pieces transcribing) → done
  const [rawStatus, setStatus] = useState('idle')
  const [seconds, setSeconds] = useState(0)
  const [level, setLevel] = useState(0)
  // One entry per piece, in order: { text } once transcribed, { failed, audio } if it failed
  const [segments, setSegments] = useState([])
  const [pending, setPending] = useState(0)
  const [error, setError] = useState('')
  const [notes, setNotes] = useState('')
  const [organizing, setOrganizing] = useState(false)
  const [draft, setDraft] = useState(loadDraft)

  const recorder = useRef(null)
  const queue = useRef(Promise.resolve())
  const pieceCount = useRef(0)

  // Once stopped, it's done when the last pieces have been transcribed
  const status = rawStatus === 'finishing' && pending === 0 ? 'done' : rawStatus

  const transcript = segments
    .map((s) => s.text)
    .filter(Boolean)
    .join('\n\n')
  const failed = segments.filter((s) => s.failed).length

  // Transcribe pieces one at a time, in order
  const transcribe = useCallback((index, audio) => {
    setPending((n) => n + 1)
    queue.current = queue.current.then(async () => {
      try {
        const { text } = await api.transcribe(audio)
        setSegments((prev) => prev.map((s, i) => (i === index ? { text } : s)))
      } catch {
        setSegments((prev) => prev.map((s, i) => (i === index ? { failed: true, audio } : s)))
      } finally {
        setPending((n) => n - 1)
      }
    })
  }, [])

  const onPiece = useCallback(
    ({ audio, silent }) => {
      const index = pieceCount.current++
      setSegments((prev) => [...prev, silent ? { text: '' } : { pending: true }])
      if (!silent) transcribe(index, audio)
    },
    [transcribe],
  )

  async function start() {
    const problem = micProblem()
    if (problem) {
      setError(problem)
      return
    }
    setError('')
    setNotes('')
    setSegments([])
    setSeconds(0)
    pieceCount.current = 0
    setStatus('starting')
    try {
      recorder.current = await startRecording({ onPiece, onLevel: setLevel, onTime: setSeconds })
      setStatus('recording')
    } catch (err) {
      setError(micErrorMessage(err))
      setStatus('idle')
    }
  }

  function pause() {
    recorder.current?.pause()
    setStatus('paused')
  }

  function resume() {
    recorder.current?.resume()
    setStatus('recording')
  }

  function stop() {
    recorder.current?.stop()
    recorder.current = null
    setStatus('finishing')
  }

  function retryFailed() {
    segments.forEach((s, i) => {
      if (s.failed) {
        setSegments((prev) => prev.map((p, j) => (j === i ? { pending: true } : p)))
        transcribe(i, s.audio)
      }
    })
  }

  async function organize() {
    setOrganizing(true)
    setError('')
    try {
      const { notes: made } = await api.lectureNotes(transcript)
      setNotes(made)
      return made
    } catch (err) {
      setError(err.message)
      return null
    } finally {
      setOrganizing(false)
    }
  }

  // Back to idle once the recording is saved (or thrown away)
  function reset() {
    recorder.current?.stop()
    recorder.current = null
    setStatus('idle')
    setSegments([])
    setSeconds(0)
    setNotes('')
    setError('')
    saveDraft(null)
    setDraft(null)
  }

  function recoverDraft() {
    if (!draft) return
    setSegments([{ text: draft.transcript }])
    setSeconds(draft.seconds || 0)
    setNotes('')
    setStatus('done')
    setDraft(null)
  }

  function discardDraft() {
    saveDraft(null)
    setDraft(null)
  }

  // Back up the transcript as it grows
  useEffect(() => {
    if (status !== 'idle' && transcript) {
      saveDraft({ transcript, seconds, savedAt: new Date().toISOString() })
    }
  }, [status, transcript, seconds])

  // Warn before closing the tab mid-lecture
  useEffect(() => {
    if (status === 'idle') return
    const warn = (e) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [status])

  // Release the microphone if the whole app goes away
  useEffect(() => () => recorder.current?.stop(), [])

  const value = {
    status,
    active: ['starting', 'recording', 'paused', 'finishing'].includes(status),
    seconds,
    level,
    transcript,
    pending,
    failed,
    error,
    notes,
    organizing,
    draft,
    start,
    pause,
    resume,
    stop,
    retryFailed,
    organize,
    reset,
    recoverDraft,
    discardDraft,
  }
  return <RecordingContext.Provider value={value}>{children}</RecordingContext.Provider>
}
