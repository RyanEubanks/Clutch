import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { CourseSuggestions, VerifiedChip } from './Courses.jsx'
import { Badge, Egg } from './Mascot.jsx'
import Meter from './Meter.jsx'

export default function ProgressView({ user, subjects, onSubjectsChanged, onStudy, onTakeQuiz }) {
  const [progress, setProgress] = useState([])
  const [newSubject, setNewSubject] = useState('')
  const [newTopics, setNewTopics] = useState({}) // subjectId -> draft name
  const [adding, setAdding] = useState('') // course name being matched against the catalog
  const [linking, setLinking] = useState(null) // custom subject being linked to a standard course
  const [error, setError] = useState('')

  useEffect(() => {
    api.progress(user.id).then(setProgress).catch((e) => setError(e.message))
  }, [user.id, subjects])

  const byTopic = Object.fromEntries(progress.map((p) => [p.topic_id, p]))

  async function run(action) {
    setError('')
    try {
      await action()
      onSubjectsChanged()
    } catch (e) {
      setError(e.message)
    }
  }

  // Adding a course first looks for matching standard courses (see CourseSuggestions).
  function addSubject(e) {
    e.preventDefault()
    if (!newSubject.trim()) return
    setAdding(newSubject.trim())
  }

  function chooseCourse(suggestion) {
    run(async () => {
      await api.addCourse(user.id, suggestion.course.id, suggestion.as_topic ? suggestion.topic : null)
      setAdding('')
      setNewSubject('')
    })
  }

  function keepCustom() {
    run(async () => {
      await api.createSubject(user.id, adding)
      setAdding('')
      setNewSubject('')
    })
  }

  function linkCourse(suggestion) {
    run(async () => {
      await api.linkSubject(linking.id, suggestion.course.id)
      setLinking(null)
    })
  }

  function addTopic(e, subjectId) {
    e.preventDefault()
    const name = (newTopics[subjectId] || '').trim()
    if (!name) return
    run(async () => {
      await api.createTopic(subjectId, name)
      setNewTopics((d) => ({ ...d, [subjectId]: '' }))
    })
  }

  function removeSubject(s) {
    if (window.confirm(`Delete "${s.name}" and all its topics and progress?`)) {
      run(() => api.deleteSubject(s.id))
    }
  }

  const badges = progress.filter((p) => p.badge_earned_at)

  return (
    <div className="page">
      <h2>Progress</h2>
      {badges.length > 0 && (
        <div className="badge-shelf">
          {badges.map((b) => (
            <figure key={b.topic_id}>
              <Badge earned size={52} title={`${b.topic_name} badge`} />
              <figcaption>{b.topic_name}</figcaption>
            </figure>
          ))}
        </div>
      )}
      <p className="status">
        Mastery updates each time you end a session: the tutor's read of your understanding, blended
        with your own confidence rating. Reach {Math.round((progress[0]?.quiz_unlock_at ?? 0.8) * 100)}%
        to unlock a topic's quiz, and pass it to earn the badge.
      </p>
      {error && <p className="error">{error}</p>}

      {subjects.map((s) => (
        <section key={s.id} className="card">
          <div className="row">
            <div className="row-start">
              <h3>{s.name}</h3>
              <VerifiedChip course={s.course} />
              {s.course && s.course.name !== s.name && <span className="status">{s.course.name}</span>}
              {!s.course && linking?.id !== s.id && (
                <button className="link" onClick={() => setLinking(s)}>
                  find a matching course
                </button>
              )}
            </div>
            <button className="icon" title="Delete subject" onClick={() => removeSubject(s)}>
              ×
            </button>
          </div>
          {s.course?.textbook_import?.available?.length > 0 && (
            <TextbookOffer course={s.course} onImported={onSubjectsChanged} />
          )}
          {linking?.id === s.id && (
            <CourseSuggestions
              query={s.name}
              mode="link"
              onChoose={linkCourse}
              onCancel={() => setLinking(null)}
            />
          )}

          {s.topics.map((t) => {
            const p = byTopic[t.id]
            return (
              <div key={t.id} className="topic-row">
                <Egg mastery={p?.mastery ?? 0} studied={Boolean(p?.sessions_count)} />
                <div className="topic-info">
                  <strong>{t.name}</strong>
                  <span className="status">
                    {p?.sessions_count
                      ? `${p.sessions_count} session${p.sessions_count === 1 ? '' : 's'} · last ${new Date(
                          p.last_studied_at + 'Z',
                        ).toLocaleDateString()}`
                      : 'Not studied yet'}
                  </span>
                  {p?.last_gaps && <span className="gaps">Work on: {p.last_gaps}</span>}
                </div>
                <Meter label="Mastery" value={p?.mastery ?? 0} />
                {p?.badge_earned_at ? (
                  <Badge earned size={40} title={`${t.name} badge earned`} />
                ) : p?.quiz_unlocked ? (
                  <button className="small" onClick={() => onTakeQuiz(t.id)}>Take quiz</button>
                ) : (
                  <Badge size={40} title={`Quiz unlocks at ${Math.round((p?.quiz_unlock_at ?? 0.8) * 100)}% mastery`} />
                )}
                <button className="secondary" onClick={() => onStudy(t.id)}>
                  Study
                </button>
                <button className="icon" title="Delete topic" onClick={() => run(() => api.deleteTopic(t.id))}>
                  ×
                </button>
              </div>
            )
          })}

          {s.course && (
            <SuggestedTopics
              course={s.course}
              have={s.topics}
              onAdd={(name) => run(() => api.createTopic(s.id, name))}
            />
          )}

          <form className="row" onSubmit={(e) => addTopic(e, s.id)}>
            <input
              value={newTopics[s.id] || ''}
              onChange={(e) => setNewTopics((d) => ({ ...d, [s.id]: e.target.value }))}
              placeholder="New topic (e.g. Chain rule)"
            />
            <button type="submit" className="secondary">
              Add topic
            </button>
          </form>
        </section>
      ))}

      <form className="card row" onSubmit={addSubject}>
        <input
          value={newSubject}
          onChange={(e) => setNewSubject(e.target.value)}
          placeholder="New course (e.g. Algebra I, Spanish, or just Addition)"
          disabled={Boolean(adding)}
        />
        <button type="submit" disabled={Boolean(adding)}>
          Add course
        </button>
      </form>
      {adding && (
        <CourseSuggestions
          key={adding}
          query={adding}
          onChoose={chooseCourse}
          onKeep={keepCustom}
          onCancel={() => setAdding('')}
        />
      )}
    </div>
  )
}

const DISMISSED_KEY = 'clutch.textbookOffer.dismissed'

function dismissedCourses() {
  try {
    return JSON.parse(localStorage.getItem(DISMISSED_KEY) || '[]')
  } catch {
    return []
  }
}

// Offers a course's free OpenStax textbook. Importing downloads it once (needs internet),
// then quizzes use its review questions and Mother Hen reads from it, all offline.
function TextbookOffer({ course, onImported }) {
  const offer = course.textbook_import
  const [state, setState] = useState(offer.state === 'running' ? 'running' : 'idle')
  const [error, setError] = useState(offer.state === 'failed' ? offer.error : '')
  const [dismissed, setDismissed] = useState(() => dismissedCourses().includes(course.id))
  const timer = useRef(null)
  const imported = useRef(onImported) // latest callback, so polling doesn't restart on re-render
  useEffect(() => {
    imported.current = onImported
  })

  // Keep checking while an import runs (also after a page reload mid-import).
  useEffect(() => {
    if (state !== 'running') return
    let cancelled = false
    function poll() {
      api
        .textbookImportStatus(course.id)
        .then((s) => {
          if (cancelled) return
          if (s.state === 'running') {
            timer.current = setTimeout(poll, 2000)
          } else if (s.state === 'failed') {
            setState('idle')
            setError(s.error || 'The import failed.')
          } else {
            setState('done')
            imported.current()
          }
        })
        .catch((e) => {
          if (cancelled) return
          setState('idle')
          setError(e.message)
        })
    }
    timer.current = setTimeout(poll, 1500)
    return () => {
      cancelled = true
      clearTimeout(timer.current)
    }
  }, [state, course.id])

  async function start() {
    setError('')
    try {
      const s = await api.importTextbook(course.id)
      if (s.state === 'done') {
        setState('done')
        onImported()
      } else {
        setState('running')
      }
    } catch (e) {
      setError(e.message)
    }
  }

  function notNow() {
    try {
      localStorage.setItem(DISMISSED_KEY, JSON.stringify([...dismissedCourses(), course.id]))
    } catch {
      // private window: it just comes back next time
    }
    setDismissed(true)
  }

  if ((dismissed && state === 'idle' && !error) || state === 'done') return null
  const titles = offer.available.map((b) => `OpenStax ${b.title}`).join(' and ')
  return (
    <div className="textbook-offer">
      <span className="textbook-offer-icon" aria-hidden="true">📖</span>
      <div className="textbook-offer-text">
        {state === 'running' ? (
          <p>
            <strong>Downloading {titles}...</strong>{' '}
            <span className="status">This takes a few seconds to a minute. You can keep studying.</span>
          </p>
        ) : (
          <>
            <p>
              <strong>Free textbook available: {titles}.</strong> Import it to get quiz questions with the
              book's own answer keys, and let Mother Hen read from the book when she helps you.
            </p>
            <p className="status small-note">
              One-time download of the text (no images); after that it works offline. Free for
              non-commercial use (CC license).
            </p>
          </>
        )}
        {error && <p className="error">{error}</p>}
      </div>
      {state === 'idle' && (
        <div className="actions">
          <button onClick={start}>{error ? 'Try again' : 'Import it'}</button>
          <button className="link" onClick={notNow}>
            not now
          </button>
        </div>
      )}
    </div>
  )
}

// The catalog's usual topics for a course that the student hasn't added yet, as one-click chips.
function SuggestedTopics({ course, have, onAdd }) {
  const names = new Set(have.map((t) => t.name.toLowerCase()))
  const missing = course.topics.filter((t) => !names.has(t.toLowerCase()))
  if (missing.length === 0) return null
  return (
    <div className="topic-chips">
      <span className="status">Usual topics:</span>
      {missing.map((t) => (
        <button key={t} className="chip add" onClick={() => onAdd(t)}>
          + {t}
        </button>
      ))}
    </div>
  )
}
