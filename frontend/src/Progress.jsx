import { useEffect, useState } from 'react'
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
