// Records the microphone as 16 kHz mono and hands back WAV pieces short enough for the
// model to transcribe. Gemma ignores audio after about 30 seconds, so each piece is cut
// between MIN_SECONDS and MAX_SECONDS, at the quietest moment, to avoid splitting words.

const RATE = 16000
const MIN_SECONDS = 20
const MAX_SECONDS = 28
const FRAME = RATE / 10 // 100 ms; loudness is measured per frame
const SILENT_RMS = 0.006 // a piece this quiet throughout is skipped instead of transcribed

// Copies microphone samples out of the audio thread
const TAP_WORKLET = `
class Tap extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0]
    if (channel) this.port.postMessage(channel.slice(0))
    return true
  }
}
registerProcessor('clutch-tap', Tap)
`

export function formatDuration(seconds) {
  const s = Math.floor(seconds)
  const h = Math.floor(s / 3600)
  const mm = String(Math.floor((s % 3600) / 60)).padStart(h ? 2 : 1, '0')
  const ss = String(s % 60).padStart(2, '0')
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

export function micProblem() {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    return 'Recording needs the app opened at http://localhost (or over https).'
  }
  return null
}

export function micErrorMessage(err) {
  if (err?.name === 'NotAllowedError' || err?.name === 'SecurityError') {
    return 'Microphone access was blocked. Allow it from the icon in the address bar, then try again.'
  }
  if (err?.name === 'NotFoundError' || err?.name === 'OverconstrainedError') {
    return 'No microphone was found. Plug one in, then try again.'
  }
  if (err?.name === 'NotReadableError') {
    return 'The microphone is being used by another app. Close it, then try again.'
  }
  return err?.message || 'Could not start recording.'
}

function rms(samples, start, end) {
  let sum = 0
  for (let i = start; i < end; i++) sum += samples[i] * samples[i]
  return Math.sqrt(sum / Math.max(1, end - start))
}

function toWavBase64(samples) {
  const bytes = new Uint8Array(44 + samples.length * 2)
  const view = new DataView(bytes.buffer)
  const text = (at, s) => [...s].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)))
  text(0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  text(8, 'WAVE')
  text(12, 'fmt ')
  view.setUint32(16, 16, true) // fmt chunk size
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, RATE, true)
  view.setUint32(28, RATE * 2, true) // bytes per second
  view.setUint16(32, 2, true) // bytes per sample frame
  view.setUint16(34, 16, true) // bits per sample
  text(36, 'data')
  view.setUint32(40, samples.length * 2, true)
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  let binary = ''
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
  }
  return btoa(binary)
}

/**
 * Start recording. Calls onPiece({ audio, seconds, silent }) for each finished piece,
 * onLevel(0..1) about 10 times a second, and onTime(seconds recorded, not counting pauses).
 * Returns { pause, resume, stop }; stop() sends the last piece and releases the microphone.
 */
export async function startRecording({ onPiece, onLevel, onTime }) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  })
  const ctx = new AudioContext()
  try {
    const url = URL.createObjectURL(new Blob([TAP_WORKLET], { type: 'application/javascript' }))
    await ctx.audioWorklet.addModule(url)
    URL.revokeObjectURL(url)
  } catch (err) {
    stream.getTracks().forEach((t) => t.stop())
    ctx.close()
    throw err
  }
  const source = ctx.createMediaStreamSource(stream)
  // No outputs: the node still runs, and nothing is played back through the speakers
  const tap = new AudioWorkletNode(ctx, 'clutch-tap', { numberOfOutputs: 0 })
  source.connect(tap)

  // Downsample to 16 kHz by averaging each window of input samples (a simple low-pass)
  const ratio = ctx.sampleRate / RATE
  let acc = 0
  let accCount = 0
  let phase = 0

  let buffer = new Float32Array(RATE * (MAX_SECONDS + 2))
  let length = 0
  let total = 0 // samples recorded overall, for the timer
  let paused = false
  let stopped = false

  function emit(end) {
    const piece = buffer.slice(0, end)
    let loudest = 0
    for (let i = 0; i + FRAME <= piece.length; i += FRAME) loudest = Math.max(loudest, rms(piece, i, i + FRAME))
    onPiece({ audio: toWavBase64(piece), seconds: piece.length / RATE, silent: loudest < SILENT_RMS })
    buffer.copyWithin(0, end, length)
    length -= end
  }

  // Cut in the middle of the longest pause between MIN_SECONDS and MAX_SECONDS. Gaps between
  // words are as quiet as pauses between sentences, so the longest quiet run is what tells
  // them apart; cutting mid-sentence makes the model guess (and repeat) the cut-off words.
  function cutPiece() {
    const levels = []
    for (let i = MIN_SECONDS * RATE; i + FRAME <= MAX_SECONDS * RATE; i += FRAME) {
      levels.push(rms(buffer, i, i + FRAME))
    }
    const quiet = Math.min(...levels) * 1.5 + 0.005
    let best = { start: levels.length - 1, length: 0 }
    let runStart = -1
    levels.forEach((level, i) => {
      if (level <= quiet) {
        if (runStart < 0) runStart = i
        if (i - runStart + 1 > best.length) best = { start: runStart, length: i - runStart + 1 }
      } else {
        runStart = -1
      }
    })
    const middle = best.start + best.length / 2
    emit(MIN_SECONDS * RATE + Math.round(middle * FRAME))
  }

  let frameLevel = 0
  let frameCount = 0
  tap.port.onmessage = ({ data }) => {
    if (paused || stopped) return
    for (let i = 0; i < data.length; i++) {
      acc += data[i]
      accCount++
      phase += 1
      if (phase < ratio) continue
      phase -= ratio
      const sample = acc / accCount
      acc = 0
      accCount = 0
      buffer[length++] = sample
      total++
      frameLevel += sample * sample
      if (++frameCount === FRAME) {
        onLevel(Math.min(1, Math.sqrt(frameLevel / FRAME) * 6))
        onTime(total / RATE)
        frameLevel = 0
        frameCount = 0
      }
      if (length >= MAX_SECONDS * RATE) cutPiece()
    }
  }

  return {
    pause() {
      paused = true
      onLevel(0)
    },
    resume() {
      paused = false
    },
    stop() {
      if (stopped) return
      stopped = true
      tap.port.onmessage = null
      source.disconnect()
      stream.getTracks().forEach((t) => t.stop())
      ctx.close()
      if (length >= RATE / 2) emit(length) // skip a last scrap under half a second
      buffer = null
      onLevel(0)
    },
  }
}
