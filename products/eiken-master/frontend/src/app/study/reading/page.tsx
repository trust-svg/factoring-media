'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  apiEndSession,
  apiGetQuestions,
  apiRecordAttempt,
  apiStartSession,
} from '@/lib/api'
import type { Question, ReadingContent } from '@/lib/types'
import PomodoroTimer from '@/components/PomodoroTimer'

export default function ReadingPage() {
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
  const startRef = useRef<number>(Date.now())
  const questionStartRef = useRef<number>(Date.now())
  const endedRef = useRef(false)
  const sessionIdRef = useRef<string | null>(null)
  const latestRef = useRef({ correctCount: 0, attempted: 0 })

  useEffect(() => {
    Promise.all([apiStartSession('reading'), apiGetQuestions('reading', 5)])
      .then(([session, qs]) => {
        setSessionId(session.id)
        sessionIdRef.current = session.id
        setQuestions(qs)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    return () => {
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
    setDone(true)
  }

  const handleSelect = async (choiceIndex: number) => {
    if (revealed || !sessionId || !questions[index]) return
    setSelected(choiceIndex)
    const content = questions[index].content as ReadingContent
    const isCorrect = choiceIndex === content.answer
    latestRef.current.attempted += 1
    if (isCorrect) { setCorrectCount((c) => c + 1); latestRef.current.correctCount += 1 }
    const timeSpent = Math.round((Date.now() - questionStartRef.current) / 1000)
    await apiRecordAttempt(sessionId, {
      question_id: questions[index].id,
      skill: 'reading',
      user_answer: content.choices[choiceIndex],
      is_correct: isCorrect,
      time_spent_seconds: timeSpent,
    }).catch(() => {})
    setRevealed(true)
  }

  const handleNext = async () => {
    if (index + 1 >= questions.length) {
      await endSession()
    } else {
      setIndex((i) => i + 1)
      setSelected(null)
      setRevealed(false)
      questionStartRef.current = Date.now()
    }
  }

  const handleGoHome = useCallback(() => {
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
      <div className="min-h-screen flex items-center justify-center bg-blue-50">
        <div className="text-blue-400 text-sm">問題を読み込み中...</div>
      </div>
    )
  }

  if (error) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-blue-50 gap-4">
        <p className="text-red-500 text-sm">{error}</p>
        <button onClick={() => router.push('/home')} className="text-indigo-600 underline text-sm">
          ホームへ
        </button>
      </main>
    )
  }

  if (done || questions.length === 0) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-blue-50 gap-5">
        <div className="text-5xl">📖</div>
        <h2 className="text-xl font-bold text-gray-700">
          {questions.length === 0 ? '問題がありません' : 'リーディング完了！'}
        </h2>
        {questions.length > 0 && (
          <p className="text-gray-500 text-sm">
            {questions.length}問中 {correctCount}問正解
          </p>
        )}
        <button
          onClick={() => router.push('/home')}
          className="bg-indigo-600 text-white px-8 py-3 rounded-xl font-bold"
        >
          ホームへ
        </button>
      </main>
    )
  }

  const q = questions[index]
  const content = q.content as ReadingContent
  const progress = ((index + 1) / questions.length) * 100

  return (
    <main className="min-h-screen bg-blue-50 flex flex-col">
      <PomodoroTimer onBreak={handleBreak} />

      {breakDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-40">
          <div className="bg-white rounded-2xl p-6 max-w-xs mx-4 text-center">
            <div className="text-4xl mb-3">⏰</div>
            <h3 className="font-bold text-gray-800 mb-2">25分経過！</h3>
            <p className="text-gray-500 text-sm mb-4">休憩しましょう</p>
            <button
              onClick={() => router.push('/home')}
              className="w-full bg-indigo-600 text-white py-2.5 rounded-xl font-bold"
            >
              ホームへ
            </button>
          </div>
        </div>
      )}

      <div className="bg-white px-4 pt-4 pb-3 shadow-sm">
        <div className="max-w-sm mx-auto">
          <div className="flex justify-between text-xs text-gray-400 mb-1.5">
            <span>リーディング</span>
            <span>{index + 1} / {questions.length}</span>
          </div>
          <div className="w-full bg-gray-100 rounded-full h-2">
            <div
              className="bg-blue-500 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="max-w-sm mx-auto space-y-3">
          {content.passage && (
            <div className="bg-white rounded-2xl p-5 shadow-sm">
              <p className="text-xs text-gray-400 mb-2">文章</p>
              <p className="text-sm text-gray-700 leading-relaxed">{content.passage}</p>
            </div>
          )}

          <div className="bg-white rounded-2xl p-4 shadow-sm">
            <p className="text-sm font-semibold text-gray-800">{content.question}</p>
          </div>

          <div className="space-y-2">
            {content.choices.map((choice, i) => {
              let cls = 'bg-white border-gray-200'
              if (revealed) {
                if (i === content.answer) cls = 'bg-green-100 border-green-400'
                else if (i === selected) cls = 'bg-red-100 border-red-400'
              } else if (i === selected) {
                cls = 'bg-blue-100 border-blue-400'
              }
              return (
                <button
                  key={i}
                  onClick={() => handleSelect(i)}
                  disabled={revealed}
                  className={`w-full ${cls} border-2 rounded-xl px-4 py-3 text-sm text-left transition-colors disabled:cursor-default`}
                >
                  {choice}
                </button>
              )
            })}
          </div>

          {revealed && (
            <div className="bg-indigo-50 rounded-xl p-4">
              <p className="text-xs text-indigo-400 mb-1">解説</p>
              <p className="text-sm text-indigo-700">{content.explanation}</p>
            </div>
          )}

          {revealed && (
            <button
              onClick={handleNext}
              className="w-full bg-indigo-600 text-white py-3 rounded-xl font-bold"
            >
              {index + 1 >= questions.length ? '完了' : '次の問題へ'}
            </button>
          )}
        </div>
      </div>

      <div className="p-4 text-center">
        <button onClick={handleGoHome} className="text-sm text-gray-400 underline">
          ホームに戻る
        </button>
      </div>
    </main>
  )
}
