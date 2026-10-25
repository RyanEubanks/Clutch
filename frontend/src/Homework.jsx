import { useState } from 'react'
import Markdown from './Markdown.jsx'

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

export default function Homework({ homework, setHomework, onGetHelp }) {
  const [images, setImages] = useState([])
  const [guide, setGuide] = useState('')
  const [loading, setLoading] = useState('') // what we're waiting on, or ''
  const [error, setError] = useState('')

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
    })

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
          </div>
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
