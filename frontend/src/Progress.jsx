import { useEffect, useState } from 'react'
import { api } from './api'
import Meter from './Meter.jsx'

export default function ProgressView({ user, subjects, onSubjectsChanged, onStudy }) {
  const [progress, setProgress] = useState([])
  const [newSubject, setNewSubject] = useState('')
  const [newTopics, setNewTopics] = useState({}) // subjectId -> draft name
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

  function addSubject(e) {
    e.preventDefault()
    if (!newSubject.trim()) return
    run(async () => {
      await api.createSubject(user.id, newSubject)
      setNewSubject('')
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

  return (
    <div className="page">
      <h2>Progress</h2>
      <p className="status">
        Mastery updates each time you end a session: the tutor's read of your understanding, blended
        with your own confidence rating.
      </p>
      {error && <p className="error">{error}</p>}

      {subjects.map((s) => (
        <section key={s.id} className="card">
          <div className="row">
            <h3>{s.name}</h3>
            <button className="icon" title="Delete subject" onClick={() => removeSubject(s)}>
              ×
            </button>
          </div>

          {s.topics.map((t) => {
            const p = byTopic[t.id]
            return (
              <div key={t.id} className="topic-row">
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
                <button className="secondary" onClick={() => onStudy(t.id)}>
                  Study
                </button>
                <button className="icon" title="Delete topic" onClick={() => run(() => api.deleteTopic(t.id))}>
                  ×
                </button>
              </div>
            )
          })}

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
        <input value={newSubject} onChange={(e) => setNewSubject(e.target.value)} placeholder="New subject (e.g. Calculus I)" />
        <button type="submit">Add subject</button>
      </form>
    </div>
  )
}
