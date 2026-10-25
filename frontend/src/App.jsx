import { useEffect, useRef, useState } from 'react'
import './App.css'

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const bottomRef = useRef(null)

  // Scroll to the newest message whenever the chat changes
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function send() {
    const text = input.trim()
    if (!text || loading) return

    // The model has no memory, so we send the whole conversation each time
    const next = [...messages, { role: 'user', content: text }]
    setMessages(next)
    setInput('')
    setLoading(true)
    setError('')

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: next }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Request failed')
      setMessages([...next, { role: 'assistant', content: data.reply }])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function newChat() {
    setMessages([])
    setError('')
  }

  return (
    <div className="chat">
      <div className="chat-header">
        <h1>Tutor</h1>
        <button className="secondary" onClick={newChat}>New chat</button>
      </div>

      <div className="messages">
        {messages.length === 0 && (
          <p className="status">Ask about a problem you are working on.</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            {m.content}
          </div>
        ))}
        {loading && <p className="status">Thinking...</p>}
        {error && <p className="error">{error}</p>}
        <div ref={bottomRef} />
      </div>

      <div className="input-row">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder="Type your question..."
        />
        <button onClick={send} disabled={loading}>Send</button>
      </div>
    </div>
  )
}