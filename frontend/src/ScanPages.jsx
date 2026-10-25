import { loadImage } from './scan'

// Pick or photograph pages, and show them as thumbnails that can be removed.
// "Take photo" opens the camera on phones; "Choose photos" picks existing ones.
export default function ScanPages({ images, setImages, onError }) {
  async function addFiles(e) {
    const files = [...e.target.files]
    e.target.value = '' // let the same file be picked again
    try {
      const loaded = await Promise.all(files.map(loadImage))
      setImages((prev) => [...prev, ...loaded])
    } catch (err) {
      onError(err.message)
    }
  }

  return (
    <>
      <div className="actions">
        <label className="upload">
          Take photo
          <input type="file" accept="image/*" capture="environment" onChange={addFiles} />
        </label>
        <label className="upload">
          Choose photos
          <input type="file" accept="image/*" multiple onChange={addFiles} />
        </label>
      </div>
      {images.length > 0 && (
        <div className="thumbs">
          {images.map((src, i) => (
            <div key={i} className="thumb">
              <img src={src} alt={`Page ${i + 1}`} />
              <button
                type="button"
                className="remove"
                title="Remove page"
                onClick={() => setImages(images.filter((_, j) => j !== i))}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </>
  )
}
