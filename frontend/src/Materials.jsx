import { useCallback, useEffect, useState } from 'react'
import { api } from './api'

export default function MaterialsView({ user, topics }) {
  const [docs, setDocs] = useState([])
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [topicId, setTopicId] = useState('')
  const [error, setError] = useState('')

  const refresh = useCallback(() => {
    api.documents(user.id).then(setDocs).catch((e) => setError(e.message))
  }, [user.id])

  useEffect(refresh, [refresh])

  async function loadFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setContent(await file.text())
    if (!title) setTitle(file.name.replace(/\.[^.]+$/, ''))
  }

  async function save(e) {
    e.preventDefault()
    setError('')
    try {
      await api.createDocument(user.id, {
        title,
        content,
        topic_id: topicId ? Number(topicId) : null,
      })
      setTitle('')
      setContent('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function remove(id) {
    await api.deleteDocument(id).catch((e) => setError(e.message))
    refresh()
  }

  return (
    <div className="page">
      <h2>Study materials</h2>
      <p className="status">
        Notes attached to a topic are shared with the tutor in that topic's sessions.
      </p>

      <form className="card form" onSubmit={save}>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title (e.g. Lecture 4 notes)" />
        <select value={topicId} onChange={(e) => setTopicId(e.target.value)}>
          <option value="">No topic</option>
          {topics.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </select>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Paste your notes here, or load a .txt / .md file below"
          rows={8}
        />
        <div className="row">
          <input type="file" accept=".txt,.md,.markdown,text/plain" onChange={loadFile} />
          <button type="submit" disabled={!title.trim() || !content.trim()}>
            Save
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </form>

      <ul className="list">
        {docs.map((d) => (
          <li key={d.id} className="card row">
            <div>
              <strong>{d.title}</strong>
              <div className="status">
                {d.topic_name || 'No topic'} · {d.char_count.toLocaleString()} characters
              </div>
            </div>
            <button className="icon" title="Delete" onClick={() => remove(d.id)}>
              ×
            </button>
          </li>
        ))}
        {docs.length === 0 && <li className="status">No materials yet.</li>}
      </ul>
    </div>
  )
}
