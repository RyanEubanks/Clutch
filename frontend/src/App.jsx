import { useCallback, useEffect, useRef, useState } from 'react'
import { api, topicOptions } from './api'
import './App.css'

const USER_KEY = 'clutch.user'

function loadSavedUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY))
  } catch {
    return null
  }
}

function saveUser(user) {
  try {
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
    else localStorage.removeItem(USER_KEY)
  } catch {
    // Storage unavailable (private window etc.): you'll just sign in again next time.
  }
}

export default function App() {
  const [user, setUser] = useState(loadSavedUser)
  const [view, setView] = useState('chat')
  const [subjects, setSubjects] = useState([])
  const [conversations, setConversations] = useState([])
  const [activeId, setActiveId] = useState(null)
  // Changing chatKey remounts the chat panel (switching chats / starting fresh).
  const [chatKey, setChatKey] = useState(0)
  const [newChatTopic, setNewChatTopic] = useState(null)
  const [error, setError] = useState('')

  const refreshSubjects = useCallback(() => {
    if (!user) return
    api.subjects(user.id).then(setSubjects).catch((e) => setError(e.message))
  }, [user])

  const refreshConversations = useCallback(() => {
    if (!user) return
    api.conversations(user.id).then(setConversations).catch((e) => setError(e.message))
  }, [user])

  useEffect(() => {
    refreshSubjects()
    refreshConversations()
  }, [refreshSubjects, refreshConversations])

  function signIn(u) {
    saveUser(u)
    setUser(u)
  }

  function signOut() {
    saveUser(null)
    setUser(null)
    setSubjects([])
    setConversations([])
    setActiveId(null)
  }

  function openConversation(id) {
    setActiveId(id)
    setView('chat')
    setChatKey((k) => k + 1)
  }

  function newChat(topicId = null) {
    setActiveId(null)
    setNewChatTopic(topicId)
    setView('chat')
    setChatKey((k) => k + 1)
  }

  async function removeConversation(id) {
    await api.deleteConversation(id).catch((e) => setError(e.message))
    if (id === activeId) newChat()
    refreshConversations()
  }

  if (!user) return <Login onSignIn={signIn} />

  const topics = topicOptions(subjects)

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          <h1>Clutch</h1>
          <button className="link" onClick={signOut} title="Sign out">
            {user.display_name || user.username} · sign out
          </button>
        </div>

        <nav className="nav">
          {[['chat', 'Study'], ['materials', 'Materials'], ['progress', 'Progress']].map(([v, label]) => (
            <button key={v} className={view === v ? 'tab active' : 'tab'} onClick={() => setView(v)}>
              {label}
            </button>
          ))}
        </nav>

        <button onClick={() => newChat()}>+ New session</button>

        <ul className="convo-list">
          {conversations.map((c) => (
            <li key={c.id} className={c.id === activeId && view === 'chat' ? 'active' : ''}>
              <button className="convo" onClick={() => openConversation(c.id)}>
                <span className="convo-title">{c.title}</span>
                <span className="convo-meta">
                  {c.topic_name || 'General'}
                  {c.ended_at ? ' · reviewed' : ''}
                </span>
              </button>
              <button className="icon" title="Delete chat" onClick={() => removeConversation(c.id)}>
                ×
              </button>
            </li>
          ))}
          {conversations.length === 0 && <li className="status">No sessions yet.</li>}
        </ul>
      </aside>

      <main className="main">
        {error && (
          <p className="error" onClick={() => setError('')}>
            {error} (click to dismiss)
          </p>
        )}
        {view === 'chat' && (
          <ChatView
            key={chatKey}
            user={user}
            initialId={activeId}
            initialTopicId={newChatTopic}
            topics={topics}
            onCreated={(id) => {
              setActiveId(id)
              refreshConversations()
            }}
            onChanged={refreshConversations}
            onGoToProgress={() => setView('progress')}
          />
        )}
        {view === 'materials' && <MaterialsView user={user} topics={topics} />}
        {view === 'progress' && (
          <ProgressView
            user={user}
            subjects={subjects}
            onSubjectsChanged={refreshSubjects}
            onStudy={(topicId) => newChat(topicId)}
          />
        )}
      </main>
    </div>
  )
}

function Login({ onSignIn }) {
  const [username, setUsername] = useState('')
  const [error, setError] = useState('')

  async function submit(e) {
    e.preventDefault()
    if (!username.trim()) return
    try {
      onSignIn(await api.login(username.trim()))
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <form className="login" onSubmit={submit}>
      <h1>Clutch</h1>
      <p className="status">Your study tutor. Enter a username to sign in or get started.</p>
      <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Username" autoFocus />
      <button type="submit">Continue</button>
      {error && <p className="error">{error}</p>}
    </form>
  )
}

function ChatView({ user, initialId, initialTopicId, topics, onCreated, onChanged, onGoToProgress }) {
  const [convo, setConvo] = useState(null)
  const [topicId, setTopicId] = useState(initialTopicId)
  const [input, setInput] = useState('')
  const [pending, setPending] = useState('') // message waiting on the tutor
  const [loading, setLoading] = useState(Boolean(initialId))
  const [error, setError] = useState('')
  const [ending, setEnding] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    if (!initialId) return
    let cancelled = false
    api
      .conversation(initialId)
      .then((c) => !cancelled && setConvo(c))
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [initialId])

  const messages = convo?.messages ?? []

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, pending, convo?.review])

  async function send() {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    setPending(text)
    setLoading(true)
    setError('')
    try {
      let current = convo
      if (!current) {
        // Chats are created on the first message, so empty ones don't pile up.
        const created = await api.createConversation(user.id, topicId || null)
        current = { ...created, messages: [], review: null }
        setConvo(current)
        onCreated(created.id)
      }
      const r = await api.sendMessage(current.id, text)
      setConvo((prev) => ({
        ...prev,
        ...r.conversation,
        messages: [...prev.messages, r.user_message, r.assistant_message],
      }))
      onChanged()
    } catch (e) {
      setError(e.message)
      setInput(text)
    } finally {
      setPending('')
      setLoading(false)
    }
  }

  async function endSession(confidence) {
    setLoading(true)
    setError('')
    try {
      const r = await api.endConversation(convo.id, confidence)
      setConvo((prev) => ({ ...prev, review: r.review, ended_at: r.review.created_at }))
      setEnding(false)
      onChanged()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const hasStudentMessages = messages.some((m) => m.role === 'user')
  const topicLabel = convo
    ? convo.topic_name || 'General'
    : topics.find((t) => t.id === topicId)?.label

  return (
    <div className="chat">
      <div className="chat-header">
        <div>
          <h2>{convo?.title || 'New session'}</h2>
          {convo && <span className="status">{topicLabel}</span>}
        </div>
        {hasStudentMessages && !ending && (
          <button className="secondary" onClick={() => setEnding(true)} disabled={loading}>
            {convo.review ? 'Review again' : 'End session'}
          </button>
        )}
      </div>

      {!convo && !initialId && (
        <label className="topic-picker">
          Topic:{' '}
          <select value={topicId ?? ''} onChange={(e) => setTopicId(e.target.value ? Number(e.target.value) : null)}>
            <option value="">General (no topic)</option>
            {topics.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
          {topics.length === 0 && (
            <button className="link" onClick={onGoToProgress}>
              add subjects & topics to track progress
            </button>
          )}
        </label>
      )}

      <div className="messages">
        {messages.length === 0 && !pending && !loading && (
          <p className="status">Ask about a problem you are working on.</p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`bubble ${m.role}`}>
            {m.content}
          </div>
        ))}
        {pending && <div className="bubble user">{pending}</div>}
        {loading && <p className="status">{pending ? 'Thinking...' : 'Loading...'}</p>}
        {convo?.review && <ReviewCard review={convo.review} />}
        {error && <p className="error">{error}</p>}
        <div ref={bottomRef} />
      </div>

      {ending ? (
        <div className="end-panel">
          <span>How confident do you feel about this now?</span>
          <div className="confidence">
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} onClick={() => endSession(n)} disabled={loading}>
                {n}
              </button>
            ))}
            <button className="secondary" onClick={() => endSession(null)} disabled={loading}>
              Skip
            </button>
            <button className="link" onClick={() => setEnding(false)}>
              cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="input-row">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder="Type your question..."
          />
          <button onClick={send} disabled={loading}>
            Send
          </button>
        </div>
      )}
    </div>
  )
}

function ReviewCard({ review }) {
  return (
    <div className="review">
      <h3>Session review</h3>
      {review.understanding != null && (
        <Meter label="Understanding" value={review.understanding} />
      )}
      {review.confidence != null && <p>Your confidence: {review.confidence}/5</p>}
      {review.summary && <p>{review.summary}</p>}
      {review.strengths && (
        <p>
          <strong>Went well:</strong> {review.strengths}
        </p>
      )}
      {review.gaps && (
        <p>
          <strong>Work on next:</strong> {review.gaps}
        </p>
      )}
    </div>
  )
}

function Meter({ label, value }) {
  const pct = Math.round(value * 100)
  return (
    <div className="meter" title={`${label}: ${pct}%`}>
      <div className="meter-fill" style={{ width: `${pct}%` }} />
      <span>
        {label}: {pct}%
      </span>
    </div>
  )
}

function MaterialsView({ user, topics }) {
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

function ProgressView({ user, subjects, onSubjectsChanged, onStudy }) {
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
