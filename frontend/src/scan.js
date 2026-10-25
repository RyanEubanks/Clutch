// Helpers for scanning paper pages (homework or notes) with the model's vision.

const MAX_SIDE = 1600 // px; big phone photos are shrunk so uploads stay fast

// Read an image file and shrink it to a JPEG data URL
export function loadImage(file) {
  // iPhone photos are often HEIC, which most browsers (Chrome on Windows included) can't open
  if (/hei[cf]/i.test(file.type) || /\.hei[cf]$/i.test(file.name)) {
    return Promise.reject(new Error(
      `${file.name} is a HEIC photo, which this browser can't open. Save it as a JPEG first ` +
      '(on iPhone: Settings > Camera > Formats > Most Compatible).',
    ))
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error(`Could not read ${file.name}`))
    reader.onload = () => {
      const img = new Image()
      img.onerror = () => reject(new Error(`${file.name} couldn't be opened as an image. Try a JPEG or PNG.`))
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

// Suggest a title from the first line of a scan, e.g. "Calculus 1 - Homework 4: Derivatives"
export function guessTitle(text, fallback = 'Scanned notes') {
  const first = text.split('\n').find((l) => l.trim()) || ''
  const title = first.replace(/[#$*_\\]/g, '').trim()
  return title.length > 3 && title.length <= 80 ? title : `${fallback} ${new Date().toLocaleDateString()}`
}
