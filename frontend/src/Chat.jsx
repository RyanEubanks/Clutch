import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import Markdown from './Markdown.jsx'
import { Badge, Hen } from './Mascot.jsx'
import Meter from './Meter.jsx'

// One study session. Messages are saved in the database as they're sent; a new chat
// is only created on its first message, so empty ones don't pile up.
export default function Chat({
  user,
  initialId,
  initialTopicId,
  topics,
  homework,
  homeworkTitle,
  onClearHomework,
  onCreated,
  onChanged,
  onGoToProgress,
  onTakeQuiz,
}) {
  const [convo, setConvo] = useState(null)
  const [topicId, setTopicId] = useState(initialTopicId)
  const [input, setInput] = useState('')
  const [pending, setPending] = useState('') // message waiting on the tutor
  const [loading, setLoading] = useState(Boolean(initialId))
  const [error, setError] = useState('')
  const [ending, setEnding] = useState(false)
  const [sources, setSources] = useState([]) // textbook sections behind the latest reply
  const bottomRef = useRef(null)
  // Id of a chat this panel created itself. Its first message is still being sent when
  // onCreated passes the id back as initialId, so it must not be reloaded from the server.
  const createdId = useRef(null)

  useEffect(() => {
    if (!initialId || initialId === createdId.current) return
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

  // Scroll to the newest message whenever the chat changes
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
        const created = await api.createConversation(user.id, topicId || null)
        current = { ...created, messages: [], review: null }
        createdId.current = created.id
        setConvo(current)
        onCreated(created.id)
      }
      const r = await api.sendMessage(current.id, text, homework)
      setConvo((prev) => ({
        ...prev,
        ...r.conversation,
        messages: [...prev.messages, r.user_message, r.assistant_message],
      }))
      setSources(r.textbook_sources ?? [])
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
      setConvo((prev) => ({
        ...prev,
        review: r.review,
        ended_at: r.review.created_at,
        quiz_unlocked: r.quiz_unlocked,
      }))
      setEnding(false)
      onChanged()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const hasStudentMessages = messages.some((m) => m.role === 'user')

  return (
    <div className="chat">
      <div className="chat-header">
        <div>
          <h2>{convo?.title || 'New session'}</h2>
          {convo && <span className="status">{convo.topic_name || 'General'}</span>}
        </div>
        {hasStudentMessages && !ending && (
          <button className="secondary" onClick={() => setEnding(true)} disabled={loading}>
            {convo.review ? 'Review again' : 'End session'}
          </button>
        )}
      </div>

      {homework && (
        <div className="context-bar">
          {homeworkTitle ? `Studying "${homeworkTitle}"` : 'Studying your homework'}
          <button className="link" onClick={onClearHomework}>Stop using it</button>
        </div>
      )}

      {convo?.textbooks?.length > 0 && <TextbookBar books={convo.textbooks} sources={sources} />}

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
          <div className="empty">
            <Hen pose="wave" size={150} />
            <p>
              {homework
                ? "Cluck cluck! Which homework problem should we work on?"
                : "Cluck cluck! I'm Mother Hen. What are you working on today?"}
            </p>
          </div>
        )}
        {messages.map((m) =>
          m.role === 'assistant' ? (
            <div key={m.id} className="msg-row">
              <Hen pose="avatar" size={36} className="avatar" />
              <div className="bubble assistant">
                <Markdown>{m.content}</Markdown>
              </div>
            </div>
          ) : (
            <div key={m.id} className="bubble user">
              {m.content}
            </div>
          ),
        )}
        {pending && <div className="bubble user">{pending}</div>}
        {loading && pending && (
          <div className="msg-row thinking">
            <Hen pose="thinking" size={56} />
            <span className="status">Mother Hen is thinking...</span>
          </div>
        )}
        {loading && !pending && <p className="status">Loading...</p>}
        {convo?.review && <ReviewCard review={convo.review} />}
        {convo?.quiz_unlocked && (
          <div className="unlock">
            <Badge size={56} />
            <div>
              <strong>Quiz unlocked!</strong>
              <p>You've mastered {convo.topic_name}. Pass the quiz to earn its badge.</p>
            </div>
            <button onClick={() => onTakeQuiz(convo.topic_id)}>Take the quiz</button>
          </div>
        )}
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

// Credit line for the OpenStax book(s) the tutor reads from (their license asks for it).
function TextbookBar({ books, sources }) {
  return (
    <div className="context-bar textbook-bar">
      <span>
        📖 Mother Hen is reading from{' '}
        {books.map((b, i) => (
          <span key={b.slug}>
            {i > 0 && ', '}
            <a href={b.url} target="_blank" rel="noreferrer" title={b.attribution}>
              OpenStax {b.title}
            </a>{' '}
            <span className="status">({b.license})</span>
          </span>
        ))}
      </span>
      {sources.length > 0 && (
        <span className="status">Last answer used: {sources.map((s) => s.section).join('; ')}</span>
      )}
    </div>
  )
}

function ReviewCard({ review }) {
  const great = review.understanding != null && review.understanding >= 0.75
  return (
    <div className="review">
      <Hen pose={great ? 'happy' : 'proud'} size={84} className="review-hen" />
      <h3>{great ? 'Egg-cellent work!' : 'Session review'}</h3>
      {review.understanding != null && <Meter label="Understanding" value={review.understanding} />}
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
