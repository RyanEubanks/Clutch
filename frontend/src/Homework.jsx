import { useState } from 'react'
import { api } from './api'
import Markdown from './Markdown.jsx'
import { TopicSelect } from './Materials.jsx'

const MAX_SIDE = 1600 // px; big phone photos are shrunk so uploads stay fast

// Read an image file and shrink it to a JPEG data URL
function loadImage(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error(`Could not read ${file.name}`))
    reader.onload = () => {
      const img = new Image()
      img.onerror = () => reject(new Error(`${file.name} is not an image`))
      img.onload = () => {
        const scale = Math.min(1, MAX_SIDE / Math.max(img.width, img.height))
        const canvas = document.createElement('canvas')
        canvas.width = Math.round(img.width * scale)
        canvas.height = Math.round(img.height * scale)
        canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height)
        resolve(canvas.toDataURL('image/jpeg', 0.85))
      }
      img.src = reader.result
    }
    reader.readAsDataURL(file)
  })
}

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

// Suggest a title from the first line of the scan, e.g. "Calculus 1 - Homework 4: Derivatives"
function guessTitle(text) {
  const first = text.split('\n').find((l) => l.trim()) || ''
  const title = first.replace(/[#$*_\\]/g, '').trim()
  return title.length > 3 && title.length <= 80 ? title : `Scanned notes ${new Date().toLocaleDateString()}`
}

export default function Homework({ user, topics, homework, setHomework, onGetHelp, onOpenMaterial }) {
  const [images, setImages] = useState([])
  const [guide, setGuide] = useState('')
  const [loading, setLoading] = useState('') // what we're waiting on, or ''
  const [error, setError] = useState('')
  const [saveForm, setSaveForm] = useState(null) // { title, topicId } while saving to Materials
  const [savedDoc, setSavedDoc] = useState(null)

  async function addFiles(e) {
    const files = [...e.target.files]
    e.target.value = '' // let the same file be picked again
    try {
      const loaded = await Promise.all(files.map(loadImage))
      setImages((prev) => [...prev, ...loaded])
    } catch (err) {
      setError(err.message)
    }
  }

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
        <label className="upload">
          Add pages
          <input type="file" accept="image/*" capture="environment" multiple onChange={addFiles} />
        </label>
        {images.length > 0 && (
          <>
            <div className="thumbs">
              {images.map((src, i) => (
                <div key={i} className="thumb">
                  <img src={src} alt={`Page ${i + 1}`} />
                  <button
                    className="remove"
                    title="Remove page"
                    onClick={() => setImages(images.filter((_, j) => j !== i))}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
            <button onClick={readHomework} disabled={!!loading}>
              Read homework
            </button>
          </>
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
