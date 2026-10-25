import { useCallback, useEffect, useState } from 'react'
import { api, topicOptions } from './api'
import './App.css'
import Chat from './Chat.jsx'
import Homework from './Homework.jsx'
import Materials from './Materials.jsx'
import { Logo } from './Mascot.jsx'
import Planner from './Planner.jsx'
import Progress from './Progress.jsx'
import Quiz from './Quiz.jsx'
import SignIn from './SignIn.jsx'
import { formatDuration } from './recorder'
import { useRecording } from './useRecording'

const VIEWS = [
  ['chat', 'Study'],
  ['planner', 'Planner'],
  ['homework', 'Homework'],
  ['materials', 'Materials'],
  ['progress', 'Progress'],
]

export default function App() {
  // undefined while checking with the server, null when nobody is signed in
  const [user, setUser] = useState(undefined)
  const recording = useRecording()
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

  // Who's signed in is the server's call (a cookie it set), not something saved in the browser
  const { setOwner } = recording
  useEffect(() => {
    api
      .session()
      .then((u) => {
        setUser(u)
        setOwner(u.id)
      })
      .catch(() => setUser(null))
  }, [setOwner])

  function signIn(u) {
    clearSession()
    setView('chat')
    setUser(u)
    recording.setOwner(u.id)
  }

  const clearSession = useCallback(() => {
    setUser(null)
    setSubjects([])
    setConversations([])
    setActiveId(null)
    setHomework('')
    setHomeworkTitle('')
  }, [])

  // Any request answered "please sign in" (e.g. the sign-in ended) lands back on the picker
  useEffect(() => {
    window.addEventListener('clutch:signed-out', clearSession)
    return () => window.removeEventListener('clutch:signed-out', clearSession)
  }, [clearSession])

  async function signOut() {
    if (recording.status !== 'idle') {
      const ok = window.confirm(
        recording.active
          ? 'A lecture is still being recorded. Signing out stops it and throws away its transcript.'
          : "This lecture's transcript hasn't been saved to Materials. Sign out and throw it away?",
      )
      if (!ok) return
      recording.reset()
    }
    recording.setOwner(null)
    await api.signOut().catch(() => {})
    clearSession()
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

  if (user === undefined) return null // checking whether someone is signed in
  if (!user) return <SignIn onSignIn={signIn} />

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
