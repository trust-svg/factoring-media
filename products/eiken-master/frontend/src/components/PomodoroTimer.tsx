'use client'

import { memo, useEffect, useRef, useState } from 'react'

export function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0')
  const s = (seconds % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}

interface PomodoroTimerProps {
  onBreak: () => void
}

export default memo(function PomodoroTimer({ onBreak }: PomodoroTimerProps) {
  const [elapsed, setElapsed] = useState(0)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const brokeRef = useRef(false)
  const mountedRef = useRef(true)

  useEffect(() => {
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    intervalRef.current = setInterval(() => {
      setElapsed((prev) => {
        const next = prev + 1
        if (next >= 1500 && !brokeRef.current) {
          brokeRef.current = true
          if (mountedRef.current) onBreak()
        }
        return next
      })
    }, 1000)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [onBreak])

  const colorClass =
    elapsed >= 1500
      ? 'bg-red-500 text-white'
      : elapsed >= 1200
      ? 'bg-amber-400 text-gray-900'
      : 'bg-white/90 text-gray-700 shadow-sm'

  return (
    <div
      className={`fixed top-3 right-3 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold z-50 ${colorClass}`}
    >
      <span className="text-[11px]">⏱</span>
      <span className="font-mono tracking-wide">{formatTime(elapsed)}</span>
    </div>
  )
})
