import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import Meter from './Meter.jsx'

// Dates are the student's local dates as YYYY-MM-DD strings throughout
const KINDS = [
  ['exam', 'Exam'],
  ['quiz', 'Quiz'],
  ['homework', 'Homework'],
  ['other', 'Other'],
]
const KIND_LABEL = Object.fromEntries(KINDS)
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

function dayKey(d) {
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

function fromKey(key) {
  const [y, m, d] = key.split('-').map(Number)
  return new Date(y, m - 1, d)
}

function addDays(key, n) {
  const d = fromKey(key)
  d.setDate(d.getDate() + n)
  return dayKey(d)
}

function daysBetween(from, to) {
  return Math.round((fromKey(to) - fromKey(from)) / 86400000)
}

function countdown(days) {
  if (days === 0) return 'today'
  if (days === 1) return 'tomorrow'
  if (days === -1) return 'yesterday'
  return days > 0 ? `in ${days} days` : `${-days} days ago`
}

function longDate(key, opts = { weekday: 'long', month: 'long', day: 'numeric' }) {
  return fromKey(key).toLocaleDateString(undefined, opts)
}

function formatTime(t) {
  if (!t) return ''
  const [h, m] = t.split(':').map(Number)
  return new Date(2000, 0, 1, h, m).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

// The 6-week grid (Sunday first) that shows the month containing `monthKey`
function monthGrid(monthKey) {
  const first = fromKey(monthKey)
  const start = new Date(first)
  start.setDate(1 - first.getDay())
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    return dayKey(d)
  })
}

export default function Planner({ user, subjects, onStudy, onTakeQuiz }) {
  const today = dayKey(new Date())
  const [plan, setPlan] = useState(null)
  const [events, setEvents] = useState([])
  const [month, setMonth] = useState(today.slice(0, 8) + '01')
  const [selected, setSelected] = useState(null) // a day picked on the calendar
  const [form, setForm] = useState(null) // event being added or edited
  const [error, setError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  const grid = useMemo(() => monthGrid(month), [month])

  useEffect(() => {
    let cancelled = false
    api
      .planner(user.id, today, new Date().getTimezoneOffset())
      .then((p) => !cancelled && setPlan(p))
      .catch((e) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [user.id, today, refreshKey])

  useEffect(() => {
    let cancelled = false
    // The visible grid, plus the next two weeks for the "coming up" list
    const to = [grid[41], addDays(today, 14)].sort()[1]
    api
      .events(user.id, [grid[0], today].sort()[0], to)
      .then((e) => !cancelled && setEvents(e))
      .catch((e) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [user.id, grid, today, refreshKey])

  const refresh = useCallback(() => setRefreshKey((k) => k + 1), [])

  const eventsByDay = useMemo(() => {
    const map = {}
    for (const e of events) (map[e.date] ||= []).push(e)
    return map
  }, [events])

  // Next review date of each topic, to show on the calendar
  const reviewsByDay = useMemo(() => {
    const map = {}
    for (const p of plan?.upcoming || []) (map[p.due] ||= []).push(p)
    if (plan?.due.length) map[today] = plan.due
    return map
  }, [plan, today])

  const comingUp = events.filter((e) => e.date >= today && e.date <= addDays(today, 14))

  async function toggleDone(e) {
    try {
      await api.updateEvent(e.id, { done: !e.done })
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  function shiftMonth(n) {
    const d = fromKey(month)
    d.setMonth(d.getMonth() + n)
    setMonth(dayKey(d))
  }

  function newEvent(date = selected || today) {
    setForm({ kind: 'exam', title: '', date, time: '', subject_id: '', topic_ids: [], notes: '' })
  }

  function editEvent(e) {
    setForm({ ...e, time: e.time || '', notes: e.notes || '', subject_id: e.subject_id ?? '' })
  }

  return (
    <div className="planner">
      <header className="planner-head">
        <div>
          <h2>Planner</h2>
          <p className="status">{longDate(today)}</p>
        </div>
        <button onClick={() => newEvent(today)}>+ Add a date</button>
      </header>

      {error && (
        <p className="error" onClick={() => setError('')}>
          {error} (click to dismiss)
        </p>
      )}

      {plan && <MetricTiles metrics={plan.metrics} tests={plan.tests} />}

      <div className="planner-grid">
        <div className="planner-col">
          <TodayReviews plan={plan} today={today} onStudy={onStudy} onTakeQuiz={onTakeQuiz} />
          <TestReadiness
            tests={plan?.tests || []}
            onStudy={onStudy}
            onEdit={async (t) => {
              // Tests further out than the loaded range: fetch that day to get the full event
              const loaded = events.find((e) => e.id === t.id)
              const event = loaded || (await api.events(user.id, t.date, t.date)).find((e) => e.id === t.id)
              if (event) editEvent(event)
            }}
          />
        </div>

        <div className="planner-col">
          <section className="card calendar">
            <div className="calendar-head">
              <button className="icon-btn" onClick={() => shiftMonth(-1)} aria-label="Previous month">
                ‹
              </button>
              <h3>{longDate(month, { month: 'long', year: 'numeric' })}</h3>
              <button className="icon-btn" onClick={() => shiftMonth(1)} aria-label="Next month">
                ›
              </button>
              {month !== today.slice(0, 8) + '01' && (
                <button className="link" onClick={() => setMonth(today.slice(0, 8) + '01')}>
                  Today
                </button>
              )}
            </div>
            <div className="cal-grid" role="grid">
              {WEEKDAYS.map((w) => (
                <div key={w} className="cal-weekday">
                  {w}
                </div>
              ))}
              {grid.map((key) => {
                const dayEvents = eventsByDay[key] || []
                const reviews = reviewsByDay[key] || []
                const classes = ['cal-day']
                if (key.slice(0, 7) !== month.slice(0, 7)) classes.push('other-month')
                if (key === today) classes.push('today')
                if (key === selected) classes.push('selected')
                if (key < today) classes.push('past')
                return (
                  <button
                    key={key}
                    className={classes.join(' ')}
                    onClick={() => setSelected(key === selected ? null : key)}
                    aria-label={`${longDate(key)}: ${dayEvents.length} dates, ${reviews.length} reviews`}
                  >
                    <span className="cal-num">{Number(key.slice(8))}</span>
                    {dayEvents.slice(0, 2).map((e) => (
                      <span key={e.id} className={`cal-pill ${e.kind}${e.done ? ' done' : ''}`}>
                        {e.title}
                      </span>
                    ))}
                    {dayEvents.length > 2 && <span className="cal-more">+{dayEvents.length - 2} more</span>}
                    {reviews.length > 0 && key >= today && (
                      <span className="cal-reviews" title={reviews.map((r) => r.topic_name).join(', ')}>
                        {reviews.length} review{reviews.length === 1 ? '' : 's'}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
            <div className="cal-legend">
              {KINDS.map(([k, label]) => (
                <span key={k}>
                  <span className={`legend-dot ${k}`} /> {label}
                </span>
              ))}
              <span>
                <span className="legend-dot review" /> Reviews
              </span>
            </div>
          </section>

          {selected ? (
            <DayPanel
              day={selected}
              today={today}
              events={eventsByDay[selected] || []}
              reviews={selected >= today ? reviewsByDay[selected] || [] : []}
              onAdd={() => newEvent(selected)}
              onEdit={editEvent}
              onToggle={toggleDone}
              onClose={() => setSelected(null)}
            />
          ) : (
            <section className="card">
              <h3>Coming up · next 2 weeks</h3>
              {comingUp.length === 0 && (
                <p className="status">Nothing on the calendar. Add your exams, quizzes and homework.</p>
              )}
              <ul className="event-list">
                {comingUp.map((e) => (
                  <EventRow key={e.id} event={e} today={today} onEdit={editEvent} onToggle={toggleDone} />
                ))}
              </ul>
            </section>
          )}

          {plan && <ActivityStrip activity={plan.metrics.activity} />}
        </div>
      </div>

      {form && (
        <EventForm
          user={user}
          subjects={subjects}
          initial={form}
          onClose={() => setForm(null)}
          onSaved={() => {
            setForm(null)
            refresh()
          }}
        />
      )}
    </div>
  )
}

function MetricTiles({ metrics, tests }) {
  const next = tests[0]
  return (
    <div className="metric-tiles">
      <div className="tile">
        <span className="tile-label">Study streak</span>
        <span className="tile-value">
          {metrics.streak} day{metrics.streak === 1 ? '' : 's'}
        </span>
        <span className="tile-note">
          {metrics.studied_today
            ? 'You studied today'
            : metrics.streak
              ? 'Study today to keep it going'
              : 'Start one today'}
        </span>
      </div>
      <div className="tile">
        <span className="tile-label">This week</span>
        <span className="tile-value">
          {metrics.week.sessions} session{metrics.week.sessions === 1 ? '' : 's'}
        </span>
        <span className="tile-note">
          {metrics.week.quizzes_taken
            ? `${metrics.week.quizzes_passed} of ${metrics.week.quizzes_taken} quizzes passed`
            : `${metrics.active_days} active days in the last 4 weeks`}
        </span>
      </div>
      <div className="tile">
        <span className="tile-label">Average mastery</span>
        <span className="tile-value">
          {metrics.average_mastery == null ? '—' : `${Math.round(metrics.average_mastery * 100)}%`}
        </span>
        <span className="tile-note">
          {metrics.topics_mastered} of {metrics.topics_total} topics mastered
        </span>
      </div>
      <div className={next?.at_risk ? 'tile at-risk' : 'tile'}>
        <span className="tile-label">Next exam or quiz</span>
        <span className="tile-value">{next ? countdown(next.days_left) : 'None'}</span>
        <span className="tile-note">
          {next
            ? `${next.title}${next.readiness != null ? ` · ${Math.round(next.readiness * 100)}% ready` : ''}`
            : 'Add one to plan reviews around it'}
        </span>
      </div>
    </div>
  )
}

function TodayReviews({ plan, today, onStudy, onTakeQuiz }) {
  if (!plan) return <section className="card"><p className="status">Loading your plan...</p></section>
  const soon = plan.upcoming.slice(0, 5)
  return (
    <section className="card">
      <h3>
        Today's reviews {plan.due.length > 0 && <span className="count">{plan.due.length}</span>}
      </h3>
      <p className="status">
        Spaced repetition: each topic comes back just before you'd start to forget it, and more
        often as an exam on it gets close.
      </p>
      {plan.due.length === 0 && plan.upcoming.length === 0 && (
        <p className="status">Add subjects and topics on the Progress tab to get a study plan.</p>
      )}
      {plan.due.length === 0 && plan.upcoming.length > 0 && (
        <p className="all-done">You're all caught up for today.</p>
      )}
      <ul className="review-list">
        {plan.due.map((p) => (
          <ReviewItem key={p.topic_id} item={p} onStudy={onStudy} onTakeQuiz={onTakeQuiz} />
        ))}
      </ul>
      {soon.length > 0 && (
        <>
          <h4>Next up</h4>
          <ul className="soon-list">
            {soon.map((p) => (
              <li key={p.topic_id}>
                <span>
                  {p.topic_name} <span className="status">· {p.subject_name}</span>
                </span>
                <span className="status">{countdown(daysBetween(today, p.due))}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

function ReviewItem({ item, onStudy, onTakeQuiz }) {
  return (
    <li className={item.test ? 'review-item has-test' : 'review-item'}>
      <div className="review-main">
        <strong>{item.topic_name}</strong> <span className="status">· {item.subject_name}</span>
        <div className="review-reasons">{item.reasons.join(' · ')}</div>
        <div className="mini-bar" title={`Mastery ${Math.round(item.mastery * 100)}%`}>
          <span style={{ width: `${Math.round(item.mastery * 100)}%` }} />
        </div>
      </div>
      <div className="review-actions">
        <button onClick={() => onStudy(item.topic_id)}>Study</button>
        {item.quiz_unlocked && (
          <button className="secondary" onClick={() => onTakeQuiz(item.topic_id)}>
            Quiz
          </button>
        )}
      </div>
    </li>
  )
}

function TestReadiness({ tests, onStudy, onEdit }) {
  if (!tests.length) return null
  return (
    <section className="card">
      <h3>Exams & quizzes</h3>
      <ul className="test-list">
        {tests.map((t) => (
          <li key={t.id} className={t.at_risk ? 'test-card at-risk' : 'test-card'}>
            <div className="row">
              <div>
                <span className={`kind-chip ${t.kind}`}>{KIND_LABEL[t.kind]}</span> <strong>{t.title}</strong>
                <div className="status">
                  {longDate(t.date, { weekday: 'short', month: 'short', day: 'numeric' })}
                  {t.time ? ` at ${formatTime(t.time)}` : ''} · {countdown(t.days_left)}
                </div>
              </div>
              {t.at_risk && <span className="risk-tag">Needs work</span>}
            </div>
            {t.readiness == null ? (
              <p className="status">
                Add the topics it covers to track how ready you are.{' '}
                <button className="link" onClick={() => onEdit(t)}>
                  Add topics
                </button>
              </p>
            ) : (
              <>
                <Meter label="Ready" value={t.readiness} />
                <ul className="weak-topics">
                  {t.topics.slice(0, 3).map((topic) => (
                    <li key={topic.topic_id}>
                      <span>
                        {topic.topic_name} <span className="status">{Math.round(topic.mastery * 100)}%</span>
                      </span>
                      <button className="link" onClick={() => onStudy(topic.topic_id)}>
                        Study
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

function EventRow({ event, today, onEdit, onToggle }) {
  return (
    <li className={event.done ? 'event-row done' : 'event-row'}>
      {event.kind === 'homework' ? (
        <input
          type="checkbox"
          checked={event.done}
          onChange={() => onToggle(event)}
          aria-label={`Mark ${event.title} ${event.done ? 'not done' : 'done'}`}
        />
      ) : (
        <span className={`legend-dot ${event.kind}`} />
      )}
      <button className="event-title" onClick={() => onEdit(event)}>
        <span>{event.title}</span>
        <span className="status">
          {KIND_LABEL[event.kind]}
          {event.subject_name ? ` · ${event.subject_name}` : ''} ·{' '}
          {longDate(event.date, { weekday: 'short', month: 'short', day: 'numeric' })}
          {event.time ? ` ${formatTime(event.time)}` : ''}
        </span>
      </button>
      <span className="when">{countdown(daysBetween(today, event.date))}</span>
    </li>
  )
}

function DayPanel({ day, today, events, reviews, onAdd, onEdit, onToggle, onClose }) {
  return (
    <section className="card">
      <div className="row">
        <h3>{longDate(day)}</h3>
        <button className="link" onClick={onClose}>
          close
        </button>
      </div>
      {events.length === 0 && reviews.length === 0 && <p className="status">Nothing planned.</p>}
      <ul className="event-list">
        {events.map((e) => (
          <EventRow key={e.id} event={e} today={today} onEdit={onEdit} onToggle={onToggle} />
        ))}
      </ul>
      {reviews.length > 0 && (
        <p className="status">
          Reviews: {reviews.map((r) => r.topic_name).join(', ')}
        </p>
      )}
      <button className="secondary" onClick={onAdd}>
        + Add on this day
      </button>
    </section>
  )
}

function ActivityStrip({ activity }) {
  const most = Math.max(1, ...activity.map((d) => d.messages))
  return (
    <section className="card">
      <h3>Last 4 weeks</h3>
      <div className="activity-strip">
        {activity.map((d) => {
          const level = d.messages === 0 ? 0 : Math.ceil((d.messages / most) * 4)
          return (
            <span
              key={d.date}
              className={`act act-${level}`}
              title={`${longDate(d.date, { weekday: 'short', month: 'short', day: 'numeric' })}: ${
                d.messages ? `${d.messages} messages in ${d.sessions} session${d.sessions === 1 ? '' : 's'}` : 'no study'
              }`}
            />
          )
        })}
      </div>
      <div className="activity-scale status">
        <span>4 weeks ago</span>
        <span>today</span>
      </div>
    </section>
  )
}

function EventForm({ user, subjects, initial, onClose, onSaved }) {
  const [form, setForm] = useState(initial)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const set = (changes) => setForm((f) => ({ ...f, ...changes }))
  const isTest = form.kind === 'exam' || form.kind === 'quiz'
  const subject = subjects.find((s) => s.id === Number(form.subject_id))
  const topicGroups = subject ? [subject] : subjects

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  function toggleTopic(id) {
    set({ topic_ids: form.topic_ids.includes(id) ? form.topic_ids.filter((t) => t !== id) : [...form.topic_ids, id] })
  }

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    setError('')
    const body = {
      kind: form.kind,
      title: form.title,
      date: form.date,
      time: form.time || null,
      notes: form.notes,
      subject_id: form.subject_id === '' ? null : Number(form.subject_id),
      topic_ids: isTest ? form.topic_ids : [],
    }
    try {
      if (form.id) await api.updateEvent(form.id, body)
      else await api.createEvent(user.id, body)
      onSaved()
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  async function remove() {
    if (!window.confirm(`Delete "${form.title}" from your calendar?`)) return
    try {
      await api.deleteEvent(form.id)
      onSaved()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form className="card form event-form" role="dialog" aria-modal="true" aria-label="Calendar date" onSubmit={save}>
        <h3>{form.id ? 'Edit date' : 'Add a date'}</h3>
        <div className="mode-tabs">
          {KINDS.map(([k, label]) => (
            <button
              key={k}
              type="button"
              className={form.kind === k ? 'mode-tab active' : 'mode-tab'}
              onClick={() => set({ kind: k })}
            >
              {label}
            </button>
          ))}
        </div>
        <input
          value={form.title}
          onChange={(e) => set({ title: e.target.value })}
          placeholder={isTest ? 'e.g. Midterm 2' : form.kind === 'homework' ? 'e.g. Problem set 5' : 'Title'}
          autoFocus
        />
        <div className="form-row">
          <label>
            Date
            <input type="date" value={form.date} onChange={(e) => set({ date: e.target.value })} required />
          </label>
          <label>
            Time <span className="status">(optional)</span>
            <input type="time" value={form.time} onChange={(e) => set({ time: e.target.value })} />
          </label>
        </div>
        <label>
          Subject <span className="status">(optional)</span>
          <select value={form.subject_id} onChange={(e) => set({ subject_id: e.target.value, topic_ids: [] })}>
            <option value="">None</option>
            {subjects.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        {isTest && (
          <fieldset className="topic-picks">
            <legend>Topics it covers</legend>
            <p className="status">Reviews of these topics get packed in before the {form.kind}.</p>
            {topicGroups.every((s) => !s.topics.length) && (
              <p className="status">Add topics on the Progress tab first.</p>
            )}
            {topicGroups.map((s) =>
              s.topics.length ? (
                <div key={s.id} className="topic-group">
                  {!subject && <span className="topic-group-name">{s.name}</span>}
                  {s.topics.map((t) => (
                    <label key={t.id} className="check">
                      <input type="checkbox" checked={form.topic_ids.includes(t.id)} onChange={() => toggleTopic(t.id)} />
                      {t.name}
                    </label>
                  ))}
                </div>
              ) : null,
            )}
          </fieldset>
        )}
        <textarea
          value={form.notes}
          onChange={(e) => set({ notes: e.target.value })}
          placeholder="Notes (room, chapters, what to bring...)"
          rows={2}
        />
        {error && <p className="error">{error}</p>}
        <div className="row">
          {form.id ? (
            <button type="button" className="secondary danger" onClick={remove}>
              Delete
            </button>
          ) : (
            <span />
          )}
          <div className="actions">
            <button type="button" className="secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" disabled={saving || !form.title.trim() || !form.date}>
              {saving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
