// Lightweight AudioContext sound effects — no external files needed
let ctx: AudioContext | null = null

function getCtx(): AudioContext {
  if (!ctx) ctx = new AudioContext()
  return ctx
}

function playTone(
  frequency: number,
  duration: number,
  gainPeak: number,
  type: OscillatorType = 'sine',
  startDelay = 0,
) {
  try {
    const ac = getCtx()
    const osc = ac.createOscillator()
    const gain = ac.createGain()
    osc.connect(gain)
    gain.connect(ac.destination)
    osc.type = type
    osc.frequency.value = frequency
    const t = ac.currentTime + startDelay
    gain.gain.setValueAtTime(0, t)
    gain.gain.linearRampToValueAtTime(gainPeak, t + 0.02)
    gain.gain.linearRampToValueAtTime(0, t + duration)
    osc.start(t)
    osc.stop(t + duration)
  } catch {
    // silently ignore (e.g. AudioContext suspended or blocked)
  }
}

export function playCorrect() {
  // Ascending two-tone chime
  playTone(523, 0.15, 0.25, 'sine', 0)    // C5
  playTone(784, 0.2, 0.22, 'sine', 0.12)  // G5
}

export function playIncorrect() {
  // Low descending buzz
  playTone(200, 0.12, 0.2, 'sawtooth', 0)
  playTone(150, 0.15, 0.15, 'sawtooth', 0.1)
}
