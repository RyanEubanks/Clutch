import { useState } from 'react'
import './App.css'
import Chat from './Chat.jsx'
import Homework from './Homework.jsx'

export default function App() {
  const [tab, setTab] = useState('chat')
  const [messages, setMessages] = useState([])
  // Text of the scanned homework; when set, the tutor keeps the chat on this material
  const [homework, setHomework] = useState('')

  function newChat() {
    setMessages([])
  }

  function getHelp() {
    setMessages([])
    setTab('chat')
  }

  return (
    <div className="chat">
      <div className="chat-header">
        <h1>Tutor</h1>
        <div className="tabs">
          <button className={tab === 'chat' ? 'tab active' : 'tab'} onClick={() => setTab('chat')}>
            Chat
          </button>
          <button
            className={tab === 'homework' ? 'tab active' : 'tab'}
            onClick={() => setTab('homework')}
          >
            Homework
          </button>
        </div>
        {tab === 'chat' && (
          <button className="secondary" onClick={newChat}>New chat</button>
        )}
      </div>

      {tab === 'chat' && homework && (
        <div className="context-bar">
          Studying your homework
          <button className="link" onClick={() => setHomework('')}>Stop using it</button>
        </div>
      )}

      {tab === 'chat' ? (
        <Chat messages={messages} setMessages={setMessages} homework={homework} />
      ) : (
        <Homework homework={homework} setHomework={setHomework} onGetHelp={getHelp} />
      )}
    </div>
  )
}
