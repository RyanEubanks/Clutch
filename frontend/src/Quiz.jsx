import { useEffect, useState } from 'react'
import { api } from './api'
import Markdown from './Markdown.jsx'
import { Badge, Hen } from './Mascot.jsx'

const LETTERS = ['A', 'B', 'C', 'D']

// How a question's answer key was checked: [tag text, longer explanation on hover].
const CHECKED = {
  math: ['math-checked', 'Mother Hen checked this answer key with a math engine (SymPy).'],
  science: ['calculator-checked', 'Checked with a calculator, including units, standard formulas and atomic weights.'],
  spanish: ['conjugation-checked', "Checked against Clutch's Spanish conjugation tables."],
  english: ['word-list checked', "Checked against Clutch's lists of irregular English words."],
  facts: ['from the fact bank', "This question comes from Clutch's fact bank, so its answer is right."],
  notes: ['checked against your notes', 'The answer was checked against a sentence in your own notes.'],
  textbook: ['from the textbook', 'This question and its answer key come from a free OpenStax textbook.'],
}

// A mastery quiz for one topic. Passing earns the topic's badge.
export default function Quiz({ topicId, onBack, onStudy, onBadge, onRetry }) {
  const [quiz, setQuiz] = useState(null)
  const [answers, setAnswers] = useState([])
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    api
      .startQuiz(topicId)
      .then((q) => {
        if (cancelled) return
        setQuiz(q)
        setAnswers(q.questions.map(() => null))
      })
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [topicId])

  async function submit() {
    setLoading(true)
    setError('')
    try {
      const r = await api.submitQuiz(quiz.id, answers)
      setResult(r)
      setQuiz(r.quiz)
      if (r.new_badge) onBadge()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  if (loading && !quiz) {
    return (
      <div className="page quiz">
        <div className="empty">
          <Hen pose="thinking" size={140} />
          <p>Mother Hen is writing your quiz... this can take a minute.</p>
        </div>
      </div>
    )
  }

  if (!quiz) {
    return (
      <div className="page quiz">
        <p className="error">{error}</p>
        <button className="secondary" onClick={onBack}>Back to progress</button>
      </div>
    )
  }

  const graded = Boolean(quiz.submitted_at)
  const allAnswered = answers.every((a) => a !== null)

  return (
    <div className="page quiz">
      <div className="row">
        <h2>{quiz.topic_name} quiz</h2>
        <button className="link" onClick={onBack}>back to progress</button>
      </div>

      {quiz.math_checker === false && (
        <p className="error">
          Math checking is off because SymPy isn't installed on the server, so answer keys may be
          wrong. Run <code>pip install -r requirements.txt</code> in backend/ and restart Flask.
        </p>
      )}

      {result ? (
        <ResultBanner result={result} onRetry={onRetry} onStudy={() => onStudy(quiz.topic_id)} />
      ) : (
        <p className="status">
          Answer all {quiz.total} questions. Get {quiz.needed} right to earn the
          badge. No peeking. Mother Hen believes in you!
        </p>
      )}

      <ol className="questions">
        {quiz.questions.map((q, i) => (
          <li key={i} className="card question">
            {q.verified && (
              <span className="checked" title={CHECKED[q.checked_by]?.[1] ?? CHECKED.math[1]}>
                ✓ {CHECKED[q.checked_by]?.[0] ?? CHECKED.math[0]}
              </span>
            )}
            <Markdown>{q.question}</Markdown>
            <div className="options">
              {q.options.map((opt, j) => {
                const chosen = (graded ? quiz.answers[i] : answers[i]) === j
                let cls = 'option'
                if (chosen) cls += ' chosen'
                if (graded && j === q.answer) cls += ' correct'
                if (graded && chosen && j !== q.answer) cls += ' wrong'
                return (
                  <button
                    key={j}
                    className={cls}
                    disabled={graded || loading}
                    onClick={() => setAnswers((a) => a.map((v, k) => (k === i ? j : v)))}
                  >
                    <span className="letter">{LETTERS[j]}</span>
                    <Markdown>{opt}</Markdown>
                  </button>
                )
              })}
            </div>
            {graded && q.voided && (
              <p className="status">This question was voided, so everyone gets credit for it.</p>
            )}
            {graded && q.key_set_by_hand && (
              <p className="status">This answer key was corrected by hand.</p>
            )}
            {graded && q.source && q.checked_by === 'textbook' && (
              <p className="source">
                📖 {q.source} ·{' '}
                <a href={q.source_url} target="_blank" rel="noreferrer">
                  read it free
                </a>{' '}
                · {q.source_license}
              </p>
            )}
            {graded && q.source && q.checked_by !== 'textbook' && (
              <blockquote className="source">
                From your notes: “{q.source}”
              </blockquote>
            )}
            {graded && q.explanation && !(q.source && q.explanation.startsWith('From your notes')) && (
              <div className="explanation">
                <Markdown>{q.explanation}</Markdown>
              </div>
            )}
          </li>
        ))}
      </ol>

      {error && <p className="error">{error}</p>}
      {!graded && (
        <button onClick={submit} disabled={!allAnswered || loading}>
          {loading ? 'Grading...' : allAnswered ? 'Submit quiz' : `Answer all ${quiz.total} to submit`}
        </button>
      )}
    </div>
  )
}

function ResultBanner({ result, onRetry, onStudy }) {
  const { quiz, needed, badge } = result
  if (quiz.passed) {
    return (
      <div className="result passed">
        <Badge earned size={96} />
        <div>
          <h3>
            {result.new_badge ? `You earned the ${quiz.topic_name} badge!` : `Passed again: ${quiz.score}/${quiz.total}!`}
          </h3>
          <p>
            {quiz.score}/{quiz.total} correct. Egg-cellent work. You hatched this one yourself.
          </p>
        </div>
        <Hen pose="happy" size={96} />
      </div>
    )
  }
  return (
    <div className="result">
      <Hen pose="proud" size={88} />
      <div>
        <h3>
          {quiz.score}/{quiz.total} correct. So close!
        </h3>
        <p>
          You need {needed} to earn the badge. Look over the explanations below, study a little more,
          then try a fresh quiz.
        </p>
        <div className="actions">
          <button onClick={onRetry}>Try a new quiz</button>
          <button className="secondary" onClick={onStudy}>Study this topic</button>
        </div>
      </div>
      {badge && <Badge earned size={56} />}
    </div>
  )
}
