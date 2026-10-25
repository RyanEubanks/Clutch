import { useState } from 'react'
import { api } from './api'
import Markdown from './Markdown.jsx'
import { TopicSelect } from './Materials.jsx'
import { guessTitle } from './scan'
import ScanPages from './ScanPages.jsx'

async function post(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || 'Request failed')
  return data
}

export default function Homework({ user, topics, homework, setHomework, onGetHelp, onOpenMaterial }) {
  const [images, setImages] = useState([])
  const [guide, setGuide] = useState('')
  const [loading, setLoading] = useState('') // what we're waiting on, or ''
  const [error, setError] = useState('')
  const [saveForm, setSaveForm] = useState(null) // { title, topicId } while saving to Materials
  const [savedDoc, setSavedDoc] = useState(null)

  async function run(label, fn) {
    setLoading(label)
    setError('')
    try {
      await fn()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading('')
    }
  }

  const readHomework = () =>
    run('Reading your homework...', async () => {
      const data = await post('/api/homework/read', { images })
      setHomework(data.text)
      setGuide('')
      setSavedDoc(null)
    })

  const saveToMaterials = (e) => {
    e.preventDefault()
    return run('Saving to Materials...', async () => {
      const doc = await api.createDocument(user.id, {
        title: saveForm.title,
        content: homework,
        topic_id: saveForm.topicId ? Number(saveForm.topicId) : null,
      })
      setSavedDoc(doc)
      setSaveForm(null)
    })
  }

  const makeGuide = () =>
    run('Writing your study guide...', async () => {
      const data = await post('/api/homework/study-guide', { homework })
      setGuide(data.guide)
    })

  return (
    <div className="homework">
      <section>
        <h2>1. Scan your homework</h2>
        <p className="status">Take a photo or upload pictures of each page.</p>
        <ScanPages images={images} setImages={setImages} onError={setError} />
        {images.length > 0 && (
          <button onClick={readHomework} disabled={!!loading}>
            Read homework
          </button>
        )}
      </section>

      {homework && (
        <section>
          <h2>2. Check the problems</h2>
          <p className="status">Fix anything that was read wrong. The tutor uses this text.</p>
          <textarea value={homework} onChange={(e) => setHomework(e.target.value)} rows={8} />
          <div className="preview">
            <Markdown>{homework}</Markdown>
          </div>
          <div className="actions">
            <button onClick={onGetHelp} disabled={!!loading}>Get help with these</button>
            <button className="secondary" onClick={makeGuide} disabled={!!loading}>
              Make a study guide
            </button>
            {!saveForm && (
              <button
                className="secondary"
                onClick={() => setSaveForm({ title: guessTitle(homework), topicId: '' })}
                disabled={!!loading}
              >
                Save to Materials
              </button>
            )}
          </div>
          {saveForm && (
            <form className="save-form" onSubmit={saveToMaterials}>
              <input
                value={saveForm.title}
                onChange={(e) => setSaveForm({ ...saveForm, title: e.target.value })}
                placeholder="Title"
                autoFocus
              />
              <TopicSelect
                topics={topics}
                value={saveForm.topicId}
                onChange={(topicId) => setSaveForm({ ...saveForm, topicId })}
              />
              <button type="submit" disabled={!saveForm.title.trim() || !!loading}>
                Save
              </button>
              <button type="button" className="link" onClick={() => setSaveForm(null)}>
                cancel
              </button>
            </form>
          )}
          {savedDoc && (
            <p className="saved-note">
              Saved to Materials as "{savedDoc.title}".{' '}
              <button className="link" onClick={() => onOpenMaterial(savedDoc.id)}>
                Open it
              </button>
            </p>
          )}
        </section>
      )}

      {loading && <p className="status">{loading}</p>}
      {error && <p className="error">{error}</p>}

      {guide && (
        <section className="guide">
          <h2>Study guide</h2>
          <Markdown>{guide}</Markdown>
        </section>
      )}
    </div>
  )
}
