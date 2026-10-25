import { useCallback, useEffect, useState } from 'react'
import { api, topicOptions } from './api'
import './App.css'
import Chat from './Chat.jsx'
import Homework from './Homework.jsx'
import Materials from './Materials.jsx'
import Progress from './Progress.jsx'

const USER_KEY = 'clutch.user'

const VIEWS = [
  ['chat', 'Study'],
  ['homework', 'Homework'],
  ['materials', 'Materials'],
  ['progress', 'Progress'],
]

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
  // Text of the scanned homework; when set, the tutor keeps the chat on this material
  const [homework, setHomework] = useState('')
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
    setHomework('')
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

        <nav className="tabs">
          {VIEWS.map(([v, label]) => (
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
          <Chat
            key={chatKey}
            user={user}
            initialId={activeId}
            initialTopicId={newChatTopic}
            topics={topics}
            homework={homework}
            onClearHomework={() => setHomework('')}
            onCreated={(id) => {
              setActiveId(id)
              refreshConversations()
            }}
            onChanged={refreshConversations}
            onGoToProgress={() => setView('progress')}
          />
        )}
        {view === 'homework' && (
          <div className="page">
            <Homework homework={homework} setHomework={setHomework} onGetHelp={() => newChat()} />
          </div>
        )}
        {view === 'materials' && <Materials user={user} topics={topics} />}
        {view === 'progress' && (
          <Progress
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
