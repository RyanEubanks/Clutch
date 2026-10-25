import { useCallback, useEffect, useState } from 'react'
import { api, topicOptions } from './api'
import './App.css'
import Chat from './Chat.jsx'
import Homework from './Homework.jsx'
import Materials from './Materials.jsx'
import { Hen, Logo } from './Mascot.jsx'
import Planner from './Planner.jsx'
import Progress from './Progress.jsx'
import Quiz from './Quiz.jsx'
import { formatDuration } from './recorder'
import { useRecording } from './useRecording'

const USER_KEY = 'clutch.user'

const VIEWS = [
  ['chat', 'Study'],
  ['planner', 'Planner'],
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
  const [quizTopic, setQuizTopic] = useState(null)
  const [quizKey, setQuizKey] = useState(0)
  // Text of the scanned homework; when set, the tutor keeps the chat on this material
  const [homework, setHomework] = useState('')
  // Title of the saved material being studied, when it came from Materials
  const [homeworkTitle, setHomeworkTitle] = useState('')
  // Document to open when switching to Materials; the key remounts it so it opens
  const [materialId, setMaterialId] = useState(null)
  const [materialsKey, setMaterialsKey] = useState(0)
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
    setHomeworkTitle('')
  }

  function openMaterial(id) {
    setMaterialId(id)
    setView('materials')
    setMaterialsKey((k) => k + 1)
  }

  function studyMaterial(doc) {
    setHomework(doc.content)
    setHomeworkTitle(doc.title)
    newChat(doc.topic_id)
  }

  function updateHomework(text) {
    setHomework(text)
    setHomeworkTitle('') // a new or edited scan isn't the saved material any more
  }

  function openConversation(id) {
    setActiveId(id)
    setView('chat')
    setChatKey((k) => k + 1)
  }

  function openQuiz(topicId) {
    setQuizTopic(topicId)
    setView('quiz')
    setQuizKey((k) => k + 1)
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
          <Logo height={52} />
          <button className="link" onClick={signOut} title="Sign out">
            {user.display_name || user.username} · sign out
          </button>
        </div>

        <RecordingIndicator onOpen={() => openMaterial(null)} />

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
            homeworkTitle={homeworkTitle}
            onClearHomework={() => updateHomework('')}
            onCreated={(id) => {
              setActiveId(id)
              refreshConversations()
            }}
            onChanged={refreshConversations}
            onGoToProgress={() => setView('progress')}
            onTakeQuiz={openQuiz}
          />
        )}
        {view === 'homework' && (
          <div className="page">
            <Homework
              user={user}
              topics={topics}
              homework={homework}
              setHomework={updateHomework}
              onGetHelp={() => newChat()}
              onOpenMaterial={openMaterial}
            />
          </div>
        )}
        {view === 'materials' && (
          <Materials
            key={materialsKey}
            user={user}
            topics={topics}
            openId={materialId}
            onSelect={setMaterialId}
            onStudy={studyMaterial}
          />
        )}
        {view === 'quiz' && quizTopic && (
          <Quiz
            key={quizKey}
            topicId={quizTopic}
            onBack={() => setView('progress')}
            onStudy={(topicId) => newChat(topicId)}
            onRetry={() => openQuiz(quizTopic)}
            onBadge={refreshSubjects}
          />
        )}
        {view === 'planner' && (
          <Planner
            user={user}
            subjects={subjects}
            onStudy={(topicId) => newChat(topicId)}
            onTakeQuiz={openQuiz}
          />
        )}
        {view === 'progress' && (
          <Progress
            user={user}
            subjects={subjects}
            onSubjectsChanged={refreshSubjects}
            onStudy={(topicId) => newChat(topicId)}
            onTakeQuiz={openQuiz}
          />
        )}
      </main>
    </div>
  )
}

// Shows while a lecture is being recorded (or its transcript is waiting), from any page
function RecordingIndicator({ onOpen }) {
  const rec = useRecording()
  if (rec.status === 'idle') return null
  const label =
    rec.status === 'recording'
      ? `Recording ${formatDuration(rec.seconds)}`
      : rec.status === 'paused'
        ? `Paused ${formatDuration(rec.seconds)}`
        : rec.status === 'done'
          ? 'Lecture ready to save'
          : 'Finishing transcript...'
  return (
    <button className={`rec-indicator ${rec.status}`} onClick={onOpen} title="Open the lecture recorder">
      <span className="rec-dot" /> {label}
    </button>
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
      <Hen pose="wave" size={160} className="login-hen" />
      <h1 className="wordmark">Clutch</h1>
      <p className="status">
        Mother Hen helps you work things out yourself. Enter a username to sign in or get started.
      </p>
      <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Username" autoFocus />
      <button type="submit">Continue</button>
      {error && <p className="error">{error}</p>}
    </form>
  )
}
