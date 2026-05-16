'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  apiEndSession,
  apiExplainJa,
  apiGenerateQuestion,
  apiGetQuestions,
  apiPraise,
  apiRecordAttempt,
  apiStartSession,
} from '@/lib/api'
import type { ExplainJaResponse, ListeningContent, Question } from '@/lib/types'
import PomodoroTimer from '@/components/PomodoroTimer'

function playSound(type: 'correct' | 'wrong') {
  if (typeof window === 'undefined') return
  const ctx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)()
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.connect(gain)
  gain.connect(ctx.destination)
  if (type === 'correct') {
    osc.frequency.setValueAtTime(523, ctx.currentTime)
    osc.frequency.setValueAtTime(659, ctx.currentTime + 0.1)
    osc.frequency.setValueAtTime(784, ctx.currentTime + 0.2)
    gain.gain.setValueAtTime(0.3, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5)
    osc.start(ctx.currentTime)
    osc.stop(ctx.currentTime + 0.5)
  } else {
    osc.frequency.setValueAtTime(330, ctx.currentTime)
    osc.frequency.setValueAtTime(220, ctx.currentTime + 0.15)
    gain.gain.setValueAtTime(0.3, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4)
    osc.start(ctx.currentTime)
    osc.stop(ctx.currentTime + 0.4)
  }
}

function speakText(text: string, onEnd?: () => void): void {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
    onEnd?.()
    return
  }
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'en-US'
  utterance.rate = 0.85
  utterance.pitch = 1.0
  if (onEnd) utterance.onend = onEnd
  window.speechSynthesis.speak(utterance)
}

export default function ListeningPage() {
  const router = useRouter()
  const [questions, setQuestions] = useState<Question[]>([])
  const [index, setIndex] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [correctCount, setCorrectCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const [breakDialog, setBreakDialog] = useState(false)
  const [praise, setPraise] = useState<string | null>(null)
  const [speaking, setSpeaking] = useState(false)
  const [jaExplain, setJaExplain] = useState<ExplainJaResponse | null>(null)
  const [jaLoading, setJaLoading] = useState(false)
  const startRef = useRef<number>(Date.now())
  const questionStartRef = useRef<number>(Date.now())
  const endedRef = useRef(false)
  const sessionIdRef = useRef<string | null>(null)
  const latestRef = useRef({ correctCount: 0, attempted: 0 })
  const wrongOnce = useRef<Set<string>>(new Set())

  useEffect(() => {
    Promise.all([apiStartSession('listening'), apiGetQuestions('listening', 5)])
      .then(async ([session, qs]) => {
        setSessionId(session.id)
        sessionIdRef.current = session.id
        if (qs.length > 0) {
          setQuestions(qs)
        } else {
          const generated = await apiGenerateQuestion('listening')
          setQuestions([generated])
        }
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
    return () => {
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel()
      }
      if (!endedRef.current && sessionIdRef.current) {
        const duration = Math.round((Date.now() - startRef.current) / 1000)
        apiEndSession(sessionIdRef.current, {
          duration_seconds: duration,
          questions_attempted: latestRef.current.attempted,
          correct_count: latestRef.current.correctCount,
          pomodoro_completed: false,
        }).catch(() => {})
      }
    }
  }, [])

  const handleSpeak = useCallback(() => {
    const q = questions[index]
    if (!q) return
    const content = q.content as ListeningContent
    const text = q.audio_text || content.question
    if (!text) return
    setSpeaking(true)
    speakText(text, () => setSpeaking(false))
  }, [questions, index])

  const endSession = async (pomodoro = false) => {
    if (!sessionId || endedRef.current) return
    endedRef.current = true
    const duration = Math.round((Date.now() - startRef.current) / 1000)
    await apiEndSession(sessionId, {
      duration_seconds: duration,
      questions_attempted: latestRef.current.attempted,
      correct_count: latestRef.current.correctCount,
      pomodoro_completed: pomodoro,
    }).catch(() => {})
    const total = latestRef.current.attempted
    if (total > 0) {
      const pct = latestRef.current.correctCount / total
      apiPraise({ skill: 'listening', is_passing: pct >= 0.6, score_pct: pct, streak: 0 })
        .then((r) => setPraise(r.praise))
        .catch(() => {})
    }
    setDone(true)
  }

  const handleSelect = async (choiceIndex: number) => {
    if (revealed || !sessionId || !questions[index]) return
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel()
    }
    setSpeaking(false)
    setSelected(choiceIndex)
    const content = questions[index].content as ListeningContent
    const isCorrect = choiceIndex === content.answer
    latestRef.current.attempted += 1
    if (isCorrect) {
      setCorrectCount((c) => c + 1)
      latestRef.current.correctCount += 1
    }
    playSound(isCorrect ? 'correct' : 'wrong')
    if (!isCorrect && !wrongOnce.current.has(questions[index].id)) {
      wrongOnce.current.add(questions[index].id)
      setQuestions((prev) => [...prev, prev[index]])
    }
    const timeSpent = Math.round((Date.now() - questionStartRef.current) / 1000)
    await apiRecordAttempt(sessionId, {
      question_id: questions[index].id,
      skill: 'listening',
      user_answer: content.choices[choiceIndex],
      is_correct: isCorrect,
      time_spent_seconds: timeSpent,
    }).catch(() => {})
    setRevealed(true)
    setJaExplain(null)
    setJaLoading(true)
    apiExplainJa({
      question: content.question,
      choices: content.choices,
      answer_index: content.answer,
      explanation: content.explanation,
    })
      .then(setJaExplain)
      .catch(() => {})
      .finally(() => setJaLoading(false))
  }

  const handleNext = async () => {
    if (index + 1 >= questions.length) {
      await endSession()
    } else {
      setIndex((i) => i + 1)
      setSelected(null)
      setRevealed(false)
      setJaExplain(null)
      questionStartRef.current = Date.now()
    }
  }

  const handleGoHome = useCallback(() => {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel()
    }
    if (!endedRef.current && sessionIdRef.current) {
      endedRef.current = true
      const duration = Math.round((Date.now() - startRef.current) / 1000)
      apiEndSession(sessionIdRef.current, {
        duration_seconds: duration,
        questions_attempted: latestRef.current.attempted,
        correct_count: latestRef.current.correctCount,
        pomodoro_completed: false,
      }).catch(() => {})
    }
    router.push('/home')
  }, [router])

  const handleBreak = useCallback(() => {
    setBreakDialog(true)
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel()
    }
    if (!endedRef.current && sessionIdRef.current) {
      endedRef.current = true
      const duration = Math.round((Date.now() - startRef.current) / 1000)
      apiEndSession(sessionIdRef.current, {
        duration_seconds: duration,
        questions_attempted: latestRef.current.attempted,
        correct_count: latestRef.current.correctCount,
        pomodoro_completed: true,
      }).catch(() => {})
      setDone(true)
    }
  }, [])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-green-50">
        <p className="text-green-400 text-base">問題を読み込み中...</p>
      </div>
    )
  }

  if (error) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-green-50 gap-4 px-4">
        <p className="text-red-500 text-base">{error}</p>
        <button onClick={() => router.push('/home')} className="text-indigo-600 underline text-base">ホームへ</button>
      </main>
    )
  }

  if (done || questions.length === 0) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-green-50 gap-5 px-4">
        <div className="text-6xl">🎧</div>
        <h2 className="text-2xl font-bold text-gray-700">
          {questions.length === 0 ? '問題がありません' : 'リスニング完了！'}
        </h2>
        {questions.length > 0 && (
          <p className="text-gray-500 text-lg">{questions.length}問中 {correctCount}問正解</p>
        )}
        {praise && (
          <div className="bg-amber-50 border border-amber-200 rounded-2xl px-5 py-4 max-w-sm flex gap-3 items-start">
            <span className="text-2xl">🌟</span>
            <p className="text-base text-amber-800 leading-relaxed">{praise}</p>
          </div>
        )}
        <button
          onClick={() => router.push('/home')}
          className="bg-indigo-600 text-white px-8 py-3.5 rounded-xl font-bold text-base"
        >
          ホームへ
        </button>
      </main>
    )
  }

  const q = questions[index]
  const content = q.content as ListeningContent
  const progress = ((index + 1) / questions.length) * 100

  return (
    <main className="min-h-screen bg-green-50 flex flex-col">
      <PomodoroTimer onBreak={handleBreak} />

      {breakDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-40">
          <div className="bg-white rounded-2xl p-6 max-w-xs mx-4 text-center">
            <div className="text-4xl mb-3">⏰</div>
            <h3 className="font-bold text-gray-800 mb-2 text-lg">25分経過！</h3>
            <p className="text-gray-500 mb-4">休憩しましょう</p>
            <button onClick={() => router.push('/home')} className="w-full bg-indigo-600 text-white py-3 rounded-xl font-bold">
              ホームへ
            </button>
          </div>
        </div>
      )}

      {/* Progress bar */}
      <div className="bg-white px-4 pt-4 pb-3 shadow-sm">
        <div className="max-w-lg mx-auto">
          <div className="flex justify-between text-sm text-gray-400 mb-2">
            <span className="font-bold text-green-600">🎧 リスニング</span>
            <span className="font-bold">{index + 1} / {questions.length}</span>
          </div>
          <div className="w-full bg-gray-100 rounded-full h-2.5">
            <div className="bg-green-500 h-2.5 rounded-full transition-all duration-300" style={{ width: `${progress}%` }} />
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="max-w-lg mx-auto space-y-4">

          {/* Audio player */}
          <div className="bg-white rounded-2xl p-6 shadow-sm text-center">
            <p className="text-xs text-green-600 font-black uppercase tracking-wider mb-5">
              音声を聴いて答えよう
            </p>
            <button
              onClick={handleSpeak}
              disabled={speaking}
              className={`w-24 h-24 rounded-full mx-auto flex items-center justify-center text-4xl transition-all duration-200 ${
                speaking
                  ? 'bg-green-100 cursor-default'
                  : 'bg-green-500 hover:bg-green-600 shadow-lg hover:scale-105 active:scale-95'
              }`}
            >
              {speaking ? '🔊' : '▶'}
            </button>
            <p className="text-sm text-gray-400 mt-4 font-bold">
              {speaking ? '再生中...' : 'タップして音声を聴く'}
            </p>
            {speaking && (
              <div className="flex justify-center gap-1 mt-3">
                {[0, 1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="w-1 rounded-full bg-green-400"
                    style={{
                      height: `${12 + (i % 3) * 8}px`,
                      animation: `pulse 0.8s ease-in-out ${i * 0.15}s infinite alternate`,
                    }}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Question */}
          <div className="bg-white rounded-2xl p-5 shadow-sm">
            <span className="inline-block bg-green-500 text-white text-xs font-black px-3 py-1 rounded-full mb-3">
              問題
            </span>
            <p className="text-lg font-bold text-gray-800 leading-snug">{content.question}</p>
          </div>

          {/* Choices */}
          <div className="space-y-3">
            {content.choices.map((choice, i) => {
              const labels = ['A', 'B', 'C', 'D']
              let cls = 'bg-white border-gray-200 text-gray-700'
              let labelCls = 'bg-gray-100 text-gray-500'
              let icon: string | null = null
              if (revealed) {
                if (i === content.answer) {
                  cls = 'bg-green-50 border-green-400 text-green-800'
                  labelCls = 'bg-green-500 text-white'
                  icon = '◯'
                } else if (i === selected) {
                  cls = 'bg-red-50 border-red-400 text-red-800'
                  labelCls = 'bg-red-400 text-white'
                  icon = '✗'
                }
              } else if (i === selected) {
                cls = 'bg-green-50 border-green-400 text-green-800'
                labelCls = 'bg-green-500 text-white'
              }
              return (
                <button
                  key={i}
                  onClick={() => handleSelect(i)}
                  disabled={revealed}
                  className={`w-full ${cls} border-2 rounded-2xl px-4 py-4 text-left flex items-center gap-3 transition-colors disabled:cursor-default`}
                >
                  <span className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-black shrink-0 ${labelCls}`}>
                    {labels[i]}
                  </span>
                  <span className="text-base leading-snug flex-1">{choice}</span>
                  {icon && (
                    <span className={`text-2xl font-black shrink-0 ${i === content.answer ? 'text-green-500' : 'text-red-500'}`}>
                      {icon}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          {/* Explanation */}
          {revealed && (
            <>
              <div className="bg-green-50 rounded-2xl p-5 border-l-4 border-green-400">
                <div className="flex justify-between items-center mb-2">
                  <p className="text-xs text-green-600 font-black uppercase tracking-wider">解説（英語）</p>
                  <button
                    onClick={() => speakText(content.explanation)}
                    className="text-green-400 hover:text-green-600 text-lg p-1"
                    aria-label="音声で読む"
                  >
                    🔊
                  </button>
                </div>
                <p className="text-base text-green-800 leading-relaxed">{content.explanation}</p>
              </div>

              {jaLoading ? (
                <div className="bg-emerald-50 rounded-2xl p-5 flex items-center gap-3">
                  <span className="text-emerald-400 text-xl animate-spin">◌</span>
                  <p className="text-emerald-500 text-base">日本語の解説を取得中...</p>
                </div>
              ) : jaExplain ? (
                <div className="bg-emerald-50 rounded-2xl p-5 border-l-4 border-emerald-400 space-y-3">
                  <p className="text-xs text-emerald-600 font-black uppercase tracking-wider">日本語解説</p>
                  <div className="bg-white rounded-xl px-4 py-3 flex items-center gap-3">
                    <span className="text-2xl">✅</span>
                    <div>
                      <p className="text-xs text-gray-400 mb-0.5">正解の意味</p>
                      <p className="text-base font-black text-gray-800">{jaExplain.answer_ja}</p>
                    </div>
                  </div>
                  <p className="text-base text-emerald-900 leading-relaxed">{jaExplain.explanation_ja}</p>
                </div>
              ) : null}

              <button
                onClick={handleNext}
                className="w-full bg-indigo-600 text-white py-4 rounded-2xl font-black text-base"
              >
                {index + 1 >= questions.length ? '✓ 完了！' : '次の問題へ →'}
              </button>
            </>
          )}
        </div>
      </div>

      <div className="p-4 text-center">
        <button onClick={handleGoHome} className="text-gray-400 underline text-base">ホームに戻る</button>
      </div>
    </main>
  )
}
