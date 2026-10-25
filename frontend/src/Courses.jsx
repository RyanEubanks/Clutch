import { useEffect, useState } from 'react'
import { api } from './api'
import { Hen } from './Mascot.jsx'

const UNVERIFIED_NOTE =
  "Mother Hen can still help here, but nothing checks her answers automatically. Add your " +
  'notes in Materials and quiz questions can be checked against them.'

function chipTitle(course) {
  const lines = []
  if (course?.checks?.length) lines.push('Checked:', ...course.checks.map((c) => `- ${c}`))
  if (course?.not_checked?.length) lines.push('Not checked:', ...course.not_checked.map((c) => `- ${c}`))
  return lines.join('\n')
}

// "✓ Verified", "◐ Partly verified" or "Not verified", with what is (not) checked on hover.
export function VerifiedChip({ course }) {
  if (course?.verification === 'verified') {
    return (
      <span className="chip verified" title={chipTitle(course)}>
        ✓ Verified
      </span>
    )
  }
  if (course?.verification === 'partial') {
    return (
      <span className="chip partial" title={chipTitle(course)}>
        <span className="half-dot" aria-hidden="true" /> Partly verified
      </span>
    )
  }
  return (
    <span className="chip unverified" title={course ? chipTitle(course) : UNVERIFIED_NOTE}>
      Not verified
    </span>
  )
}

// What a course's checks do and don't cover, for suggestion cards.
function CheckList({ course }) {
  return (
    <>
      {course.checks.length > 0 && (
        <ul className="checks">
          {course.checks.map((c) => (
            <li key={c}>✓ {c}</li>
          ))}
        </ul>
      )}
      {course.not_checked.length > 0 && (
        <p className="status small-note">Not checked: {course.not_checked.join('; ')}</p>
      )}
    </>
  )
}

/**
 * Standard courses that match what the student typed.
 * mode "add": add the chosen course (with the typed text as a topic when it's narrower),
 *             or keep the typed text as a custom course.
 * mode "link": link an existing custom course to the chosen standard course.
 */
export function CourseSuggestions({ query, mode = 'add', onChoose, onKeep, onCancel }) {
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    api
      .suggestCourses(query)
      .then((r) => !cancelled && setResult(r))
      .catch((e) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [query])

  if (!result && !error) {
    return (
      <div className="suggestions">
        <div className="msg-row thinking">
          <Hen pose="thinking" size={48} />
          <span className="status">Mother Hen is looking for courses that match "{query}"...</span>
        </div>
      </div>
    )
  }

  const suggestions = result?.suggestions ?? []
  return (
    <div className="suggestions">
      {error && <p className="error">{error}</p>}
      {suggestions.length > 0 ? (
        <p className="status">
          {mode === 'link'
            ? `Link "${query}" to a standard course to see how reliable its answers are:`
            : `Did you mean one of these standard courses?`}
        </p>
      ) : (
        !error && (
          <p className="status">
            No standard course matches "{query}". {mode === 'add' && 'You can still add it as your own course.'}
          </p>
        )
      )}

      {suggestions.map((s) => (
        <div key={s.course.id} className={`suggestion ${s.course.verification ? 'is-' + s.course.verification : ''}`}>
          <div className="suggestion-info">
            <div className="row-start">
              <strong>{s.course.name}</strong>
              <VerifiedChip course={s.course} />
              <span className="status">
                {s.course.area} · {s.course.level}
              </span>
            </div>
            <p>{s.why || s.course.description}</p>
            <CheckList course={s.course} />
          </div>
          <button onClick={() => onChoose(s)}>
            {mode === 'link'
              ? `Link to ${s.course.name}`
              : s.as_topic
                ? `Add ${s.course.name} with "${s.topic}"`
                : `Add ${s.course.name}`}
          </button>
        </div>
      ))}

      <div className="actions">
        {mode === 'add' && (
          <button className="secondary" onClick={onKeep}>
            Keep "{query}" as my own course
          </button>
        )}
        <button className="link" onClick={onCancel}>
          cancel
        </button>
      </div>
    </div>
  )
}
