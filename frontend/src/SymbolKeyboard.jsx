import { useState } from 'react'
import { flushSync } from 'react-dom'
import { KEYBOARDS, insertKey, pickKeyboard } from './keyboards'

// A panel of symbol keys above a text box. It picks the keyboard that fits the topic (or the
// conversation so far), and the student can switch to any other. Keys type into the box at
// the cursor without taking focus away from it.
export default function SymbolKeyboard({ inputRef, value, onChange, topicLabel, contextText }) {
  const auto = pickKeyboard(topicLabel, contextText)
  const [chosen, setChosen] = useState(null) // null: follow the topic
  const id = chosen ?? auto
  const keyboard = KEYBOARDS[id]

  function press(key) {
    const el = inputRef.current
    const start = el?.selectionStart ?? value.length
    const end = el?.selectionEnd ?? value.length
    const next = insertKey(value, start, end, key.insert)
    // Render the new text right away, then put the cursor where the key says (inside the
    // brackets, etc.), so the next thing typed lands there however fast it comes
    flushSync(() => onChange(next.value))
    el?.focus()
    el?.setSelectionRange(next.caret, next.caret)
  }

  return (
    <div className="symbol-keyboard" role="toolbar" aria-label={`${keyboard.name} keyboard`}>
      <div className="kb-head">
        <select
          value={id}
          onChange={(e) => setChosen(e.target.value === auto ? null : e.target.value)}
          aria-label="Keyboard"
        >
          {Object.entries(KEYBOARDS).map(([kid, kb]) => (
            <option key={kid} value={kid}>
              {kb.name}
              {kid === auto ? ' (fits this topic)' : ''}
            </option>
          ))}
        </select>
        {chosen && (
          <button type="button" className="link" onClick={() => setChosen(null)}>
            back to {KEYBOARDS[auto].name}
          </button>
        )}
      </div>
      <div className="kb-keys">
        {keyboard.keys.map((key, i) => (
          <button
            key={`${id}-${i}`}
            type="button"
            className="kb-key"
            title={key.title || key.insert.replace('▮', '…')}
            // Keep focus (and the selection) in the text box
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => press(key)}
          >
            {key.label}
          </button>
        ))}
      </div>
    </div>
  )
}
