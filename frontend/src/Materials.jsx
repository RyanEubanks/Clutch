import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import Markdown from './Markdown.jsx'
import { formatDuration } from './recorder'
import { useRecording } from './useRecording'
import { guessTitle } from './scan'
import ScanPages from './ScanPages.jsx'

const NO_TOPIC = 'No topic'

// Group documents under "Subject / Topic", alphabetically, with untopicked ones last.
function groupDocs(docs) {
  const groups = new Map()
  for (const d of docs) {
    const label = d.topic_name ? `${d.subject_name} / ${d.topic_name}` : NO_TOPIC
    if (!groups.has(label)) groups.set(label, [])
    groups.get(label).push(d)
  }
  return [...groups].sort(([a], [b]) =>
    a === NO_TOPIC ? 1 : b === NO_TOPIC ? -1 : a.localeCompare(b),
  )
}

// Rough plain-text version of Markdown + LaTeX, for jump links and search snippets
// (both are plain text, so math can't be typeset there).
function plainMath(text) {
  let out = text.replace(/\$+/g, '')
  // Innermost first, so nested fractions and roots come out right
  for (let i = 0; i < 4; i++) {
    out = out
      .replace(/([_^])\{([^{}]*)\}/g, '$1$2')
      .replace(/\\frac\{([^{}]*)\}\{([^{}]*)\}/g, '($1)/($2)')
      .replace(/\\sqrt\{([^{}]*)\}/g, '√($1)')
  }
  return out
    .replace(/\\cdot/g, '·')
    .replace(/\\times/g, '×')
    .replace(/\\(left|right)/g, '')
    .replace(/\\([a-zA-Z]+)/g, '$1')
    .replace(/[{}*_#]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

function plainLabel(text) {
  const label = plainMath(text)
  return label.length > 48 ? `${label.slice(0, 47)}…` : label
}

// Split notes into sections at headings ("# Title") and numbered problems ("3. ..." or "3) ...")
// so the reader can offer jump links. Lines inside $$ ... $$ blocks never start a section.
function splitSections(content) {
  const sections = [{ label: null, lines: [] }]
  let inMath = false
  for (const line of content.split('\n')) {
    if (!inMath) {
      const heading = line.match(/^#{1,3}\s+(.+)/)
      const problem = line.match(/^\s{0,1}(\d+)[.)]\s+(.+)/)
      if (heading) sections.push({ label: plainLabel(heading[1]), lines: [] })
      else if (problem) sections.push({ label: `${problem[1]}. ${plainLabel(problem[2])}`, lines: [] })
    }
    sections[sections.length - 1].lines.push(line)
    if (line.trim() === '$$') inMath = !inMath
  }
  return sections
    .map((s) => ({ ...s, text: s.lines.join('\n') }))
    .filter((s) => s.label || s.text.trim())
}

function formatDate(sqlDate) {
  const d = new Date(`${sqlDate.replace(' ', 'T')}Z`)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString()
}

export default function MaterialsView({ user, topics, openId, onSelect, onStudy }) {
  const [docs, setDocs] = useState([])
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState(openId ?? null)
  const [doc, setDoc] = useState(null)
  const recording = useRecording()
  // Reopen the recorder if a lecture is being recorded (or waiting to be saved)
  const [adding, setAdding] = useState(recording.status !== 'idle')
  const [closed, setClosed] = useState(() => new Set()) // collapsed group labels
  const [error, setError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  // Search on the server; wait a moment after typing so every keystroke isn't a request
  useEffect(() => {
    let cancelled = false
    const timer = setTimeout(() => {
      api
        .documents(user.id, query)
        .then((d) => !cancelled && setDocs(d))
        .catch((e) => !cancelled && setError(e.message))
    }, query ? 250 : 0)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [user.id, query, refreshKey])

  useEffect(() => {
    onSelect?.(selectedId) // so App can reopen this document next time
    if (!selectedId) return
    let cancelled = false
    api
      .document(selectedId)
      .then((d) => !cancelled && setDoc(d))
      .catch(() => !cancelled && setSelectedId(null)) // e.g. it was deleted elsewhere
    return () => {
      cancelled = true
    }
  }, [selectedId, onSelect])

  const groups = useMemo(() => groupDocs(docs), [docs])
  const searching = Boolean(query.trim())

  function open(id) {
    setAdding(false)
    setError('')
    if (id !== selectedId) {
      setDoc(null)
      setSelectedId(id)
    }
  }

  function toggleGroup(label) {
    setClosed((prev) => {
      const next = new Set(prev)
      if (next.has(label)) next.delete(label)
      else next.add(label)
      return next
    })
  }

  async function remove(d) {
    if (!window.confirm(`Delete "${d.title}"? This can't be undone.`)) return
    try {
      await api.deleteDocument(d.id)
      setSelectedId(null)
      setDoc(null)
      setRefreshKey((k) => k + 1)
    } catch (e) {
      setError(e.message)
    }
  }

  function saved(created) {
    setRefreshKey((k) => k + 1)
    open(created.id)
  }

  const reader = adding ? (
    <AddMaterial user={user} topics={topics} onSaved={saved} onCancel={() => setAdding(false)} />
  ) : doc && doc.id === selectedId ? (
    <Reader key={doc.id} doc={doc} docs={docs} onStudy={onStudy} onDelete={remove} />
  ) : selectedId ? (
    <p className="status">Loading...</p>
  ) : (
    <div className="reader-empty">
      <p className="status">
        {docs.length || searching
          ? 'Pick a document on the left to read it here.'
          : 'No materials yet. Add notes, or save a scan from the Homework tab.'}
      </p>
    </div>
  )

  return (
    <div className="library">
      <aside className="library-list">
        <div className="row">
          <h2>Materials</h2>
          <button className="secondary" onClick={() => setAdding(true)}>
            + Add
          </button>
        </div>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search titles and notes..."
        />

        <div className="library-groups">
          {groups.map(([label, items]) => {
            const isOpen = searching || !closed.has(label)
            return (
              <section key={label} className="doc-group">
                <button className="doc-group-head" onClick={() => toggleGroup(label)} aria-expanded={isOpen}>
                  <span className="caret">{isOpen ? '▾' : '▸'}</span>
                  <span className="doc-group-label">{label}</span>
                  <span className="count">{items.length}</span>
                </button>
                {isOpen && (
                  <ul className="doc-items">
                    {items.map((d) => (
                      <li key={d.id}>
                        <button
                          className={d.id === selectedId && !adding ? 'doc-item active' : 'doc-item'}
                          onClick={() => open(d.id)}
                        >
                          <span className="doc-title">{d.title}</span>
                          {d.snippet ? (
                            <span className="doc-snippet">{plainMath(d.snippet)}</span>
                          ) : (
                            <span className="doc-meta">
                              {formatDate(d.created_at)} · {d.char_count.toLocaleString()} chars
                            </span>
                          )}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            )
          })}
          {searching && docs.length === 0 && <p className="status">No matches for "{query.trim()}".</p>}
        </div>
      </aside>

      <section className="library-reader">
        {error && (
          <p className="error" onClick={() => setError('')}>
            {error} (click to dismiss)
          </p>
        )}
        {reader}
      </section>
    </div>
  )
}

function Reader({ doc, docs, onStudy, onDelete }) {
  const [guide, setGuide] = useState('')
  const [guideLoading, setGuideLoading] = useState(false)
  const [error, setError] = useState('')
  const sections = useMemo(() => splitSections(doc.content), [doc.content])
  const jumps = sections.filter((s) => s.label)
  // The list has topic and subject names; the single-document endpoint doesn't
  const meta = docs.find((d) => d.id === doc.id)

  async function makeGuide() {
    setGuideLoading(true)
    setError('')
    try {
      setGuide((await api.studyGuide(doc.content)).guide)
    } catch (e) {
      setError(e.message)
    } finally {
      setGuideLoading(false)
    }
  }

  function jumpTo(i) {
    const el = document.getElementById(`doc-section-${i}`)
    if (!el) return
    const pane = el.closest('.library-reader')
    const start = pane?.scrollTop
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    // Some browsers skip smooth scrolling (e.g. when animations are throttled); jump instead
    setTimeout(() => {
      if (pane && pane.scrollTop === start) el.scrollIntoView({ block: 'start' })
    }, 400)
  }

  return (
    <article className="reader">
      <header className="reader-head">
        <h2>{doc.title}</h2>
        <p className="status">
          {meta?.topic_name ? `${meta.subject_name} / ${meta.topic_name}` : NO_TOPIC} ·{' '}
          {formatDate(doc.created_at)} · {doc.char_count.toLocaleString()} characters
        </p>
        <div className="actions">
          <button onClick={() => onStudy(doc)}>Study this</button>
          <button className="secondary" onClick={makeGuide} disabled={guideLoading}>
            {guideLoading ? 'Writing study guide...' : guide ? 'Redo study guide' : 'Make a study guide'}
          </button>
          <button className="secondary danger" onClick={() => onDelete(doc)}>
            Delete
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </header>

      {jumps.length > 1 && (
        <nav className="jump-bar" aria-label="Jump to section">
          <span className="jump-label">Jump to</span>
          {sections.map((s, i) =>
            s.label ? (
              <button key={i} className="jump" onClick={() => jumpTo(i)} title={s.label}>
                {s.label}
              </button>
            ) : null,
          )}
          {guide && (
            <button className="jump" onClick={() => jumpTo('guide')}>
              Study guide
            </button>
          )}
        </nav>
      )}

      <div className="reader-body">
        {sections.map((s, i) => (
          <section key={i} id={`doc-section-${i}`} className="doc-section">
            <Markdown>{s.text}</Markdown>
          </section>
        ))}
        {guide && (
          <section id="doc-section-guide" className="doc-section guide-box">
            <h3>Study guide</h3>
            <Markdown>{guide}</Markdown>
          </section>
        )}
      </div>
    </article>
  )
}

// Lecture notes, followed by the full transcript so nothing said is lost (and it's searchable)
function withTranscript(notes, transcript) {
  return `${notes.trim()}\n\n## Full transcript\n\n${transcript.trim()}`
}

const ADD_MODES = [
  ['scan', 'Scan pages'],
  ['record', 'Record lecture'],
  ['type', 'Type or paste'],
]

function AddMaterial({ user, topics, onSaved, onCancel }) {
  const recording = useRecording()
  const [mode, setMode] = useState(recording.status !== 'idle' ? 'record' : 'scan')
  const [images, setImages] = useState([]) // pages waiting to be read (or that failed)
  const [reading, setReading] = useState('') // progress message while pages are read
  const [scanError, setScanError] = useState('')
  // A lecture organized while this form was closed is picked up when it reopens
  const [title, setTitle] = useState(() =>
    recording.notes ? guessTitle(recording.notes, 'Lecture notes') : '',
  )
  const [content, setContent] = useState(() =>
    recording.notes ? withTranscript(recording.notes, recording.transcript) : '',
  )
  const [topicId, setTopicId] = useState('')
  const [error, setError] = useState('')

  function applyLectureNotes(notes) {
    setContent(withTranscript(notes, recording.transcript))
    if (!title.trim()) setTitle(guessTitle(notes, 'Lecture notes'))
  }

  // Pages are read as soon as they're added, one per request, so we can show progress
  // and keep what's done if one fails. Any pages left from a failed read go first.
  async function readNotes(pages) {
    let text = content.trim()
    let done = 0
    setScanError('')
    try {
      for (const image of pages) {
        setReading(`Reading page ${done + 1} of ${pages.length}... (about 10 seconds a page)`)
        const page = (await api.readPages([image], 'notes')).text.trim()
        if (!page) throw new Error('No text was found on that page')
        text = text ? `${text}\n\n${page}` : page
        setContent(text)
        if (!title.trim() && done === 0 && !content.trim()) setTitle(guessTitle(page))
        done++
      }
    } catch (err) {
      setScanError(`Couldn't read page ${done + 1}: ${err.message}. Pages read so far were kept.`)
    } finally {
      setImages(pages.slice(done)) // leave only the pages that weren't read, to try again
      setReading('')
    }
  }

  async function loadFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setContent(await file.text())
    if (!title) setTitle(file.name.replace(/\.[^.]+$/, ''))
  }

  async function save(e) {
    e.preventDefault()
    setError('')
    try {
      const doc = await api.createDocument(user.id, {
        title,
        content,
        topic_id: topicId ? Number(topicId) : null,
      })
      if (mode === 'record') recording.reset() // saved, so the recording and its backup can go
      onSaved(doc)
    } catch (err) {
      setError(err.message)
    }
  }

  const busy = !!reading || (mode === 'record' && recording.status !== 'idle' && recording.status !== 'done')
  // Scanning and recording fill in the editor; show it once there's something to edit
  const showEditor = mode === 'type' || Boolean(content.trim())

  return (
    <form className="card form add-material" onSubmit={save}>
      <h3>Add material</h3>
      <p className="status">
        Notes attached to a topic are shared with the tutor in that topic's sessions.
      </p>

      <div className="mode-tabs" role="tablist">
        {ADD_MODES.map(([m, label]) => (
          <button
            key={m}
            type="button"
            role="tab"
            aria-selected={mode === m}
            className={mode === m ? 'mode-tab active' : 'mode-tab'}
            onClick={() => setMode(m)}
          >
            {label}
            {m === 'record' && recording.active && <span className="rec-dot" aria-label="recording" />}
          </button>
        ))}
      </div>

      {mode === 'scan' && (
        <fieldset className="scan-box" disabled={!!reading}>
          <legend>Scan your notes</legend>
          <p className="status">
            Photograph each page. Clutch reads it right away into text below that you can fix up.
          </p>
          <ScanPages
            images={images}
            setImages={setImages}
            onError={setScanError}
            onAdded={(added) => readNotes([...images, ...added])}
          />
          {reading && <p className="scan-progress">{reading}</p>}
          {scanError && <p className="error">{scanError}</p>}
          {!reading && images.length > 0 && (
            <button type="button" onClick={() => readNotes(images)}>
              Try reading {images.length === 1 ? 'that page' : `those ${images.length} pages`} again
            </button>
          )}
        </fieldset>
      )}

      {mode === 'record' && <RecordPanel onNotes={applyLectureNotes} hasNotes={Boolean(content.trim())} />}

      {showEditor && (
        <>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title (e.g. Lecture 4 notes)" />
          <TopicSelect topics={topics} value={topicId} onChange={setTopicId} />
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Type or paste your notes here."
            rows={10}
          />
          {content.trim() && (
            <div className="preview">
              <span className="preview-label">Preview</span>
              <Markdown>{content}</Markdown>
            </div>
          )}
        </>
      )}
      <div className="row">
        {mode === 'type' ? (
          <label className="file-link">
            or load a .txt / .md file
            <input type="file" accept=".txt,.md,.markdown,text/plain" onChange={loadFile} />
          </label>
        ) : (
          <span />
        )}
        <div className="actions">
          <button type="button" className="secondary" onClick={onCancel}>
            {mode === 'record' && recording.active ? 'Close (keeps recording)' : 'Cancel'}
          </button>
          <button type="submit" disabled={!title.trim() || !content.trim() || busy}>
            Save
          </button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
    </form>
  )
}

function RecordPanel({ onNotes, hasNotes }) {
  const rec = useRecording()
  const transcriptEnd = useRef(null)

  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ block: 'nearest' })
  }, [rec.transcript])

  async function makeNotes() {
    const notes = await rec.organize()
    if (notes) onNotes(notes)
  }

  function discard() {
    if (window.confirm('Throw away this recording and its transcript?')) rec.reset()
  }

  return (
    <section className="record-box">
      {rec.status === 'idle' && rec.draft && (
        <div className="draft-note">
          <span>
            You have an unsaved lecture transcript from{' '}
            {new Date(rec.draft.savedAt).toLocaleString()}.
          </span>
          <button type="button" className="secondary" onClick={rec.recoverDraft}>
            Recover it
          </button>
          <button type="button" className="link" onClick={rec.discardDraft}>
            discard
          </button>
        </div>
      )}

      {rec.status === 'idle' && (
        <>
          <p className="status">
            Record a lecture with your microphone. Clutch transcribes it on this computer as you
            go, then turns the transcript into notes. Keep this tab open; you can use the rest of
            the app while it records.
          </p>
          <button type="button" className="record-btn" onClick={rec.start}>
            <span className="rec-dot" /> Start recording
          </button>
        </>
      )}

      {rec.status === 'starting' && <p className="status">Waiting for the microphone...</p>}

      {(rec.status === 'recording' || rec.status === 'paused') && (
        <div className="record-controls">
          <span className={rec.status === 'recording' ? 'rec-live' : 'rec-live paused'}>
            <span className="rec-dot" /> {rec.status === 'recording' ? 'Recording' : 'Paused'}
          </span>
          <span className="rec-time">{formatDuration(rec.seconds)}</span>
          <span className="level" aria-hidden="true">
            <span style={{ width: `${Math.round(rec.level * 100)}%` }} />
          </span>
          {rec.status === 'recording' ? (
            <button type="button" className="secondary" onClick={rec.pause}>
              Pause
            </button>
          ) : (
            <button type="button" className="secondary" onClick={rec.resume}>
              Resume
            </button>
          )}
          <button type="button" onClick={rec.stop}>
            Stop
          </button>
        </div>
      )}

      {rec.status !== 'idle' && rec.status !== 'starting' && (
        <div className="transcript-box">
          <span className="preview-label">
            Transcript{rec.seconds ? ` · ${formatDuration(rec.seconds)}` : ''}
            {rec.pending > 0 && ' · transcribing...'}
          </span>
          {rec.transcript ? (
            rec.transcript.split('\n\n').map((p, i) => <p key={i}>{p}</p>)
          ) : (
            <p className="status">
              {rec.status === 'done'
                ? 'No speech was picked up.'
                : 'The first lines show up about half a minute in.'}
            </p>
          )}
          <div ref={transcriptEnd} />
        </div>
      )}

      {rec.status === 'finishing' && <p className="scan-progress">Transcribing the last part...</p>}

      {rec.failed > 0 && rec.status !== 'finishing' && (
        <p className="error">
          {rec.failed === 1 ? 'One part' : `${rec.failed} parts`} of the recording couldn't be
          transcribed.{' '}
          <button type="button" className="link" onClick={rec.retryFailed}>
            Try again
          </button>
        </p>
      )}

      {rec.status === 'done' && (
        <div className="actions">
          {rec.transcript && (
            <button type="button" onClick={makeNotes} disabled={rec.organizing || rec.failed > 0}>
              {rec.organizing
                ? 'Writing notes... (about 30 seconds per 10 minutes of lecture)'
                : hasNotes
                  ? 'Redo notes from transcript'
                  : 'Turn into notes'}
            </button>
          )}
          <button type="button" className="secondary danger" onClick={discard} disabled={rec.organizing}>
            Discard recording
          </button>
        </div>
      )}

      {rec.error && <p className="error">{rec.error}</p>}
    </section>
  )
}

export function TopicSelect({ topics, value, onChange }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">No topic</option>
      {topics.map((t) => (
        <option key={t.id} value={t.id}>
          {t.label}
        </option>
      ))}
    </select>
  )
}
