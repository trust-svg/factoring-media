'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  apiEndSession,
  apiGenerateAudio,
  apiGetQuestions,
  apiRecordAttempt,
  apiStartSession,
} from '@/lib/api'
import type { ListeningContent, Question } from '@/lib/types'
import PomodoroTimer from '@/components/PomodoroTimer'

function base64ToAudioUrl(b64: string): string {
  const bytes = atob(b64)
  const arr = new Uint8Array(bytes.length)
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
  return URL.createObjectURL(new Blob([arr], { type: 'audio/mpeg' }))
}

export default function ListeningPage() {
  const router = useRouter()
  const [questions, setQuestions] = useState<Question[]>([])
  const [index, setIndex] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [correctCount, setCorrectCount] = useState(0)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [audioLoading, setAudioLoading] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const [breakDialog, setBreakDialog] = useState(false)
  const startRef = useRef<number>(Date.now())
  const questionStartRef = useRef<number>(Date.now())
  const prevAudioUrl = useRef<string | null>(null)

  useEffect(() => {
    Promise.all([apiStartSession('listening'), apiGetQuestions('listening', 5)])
      .then(([session, qs]) => {
        setSessionId(session.id)
        setQuestions(qs)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    let cancelled = false
    if (prevAudioUrl.current) {
      URL.revokeObjectURL(prevAudioUrl.current)
      prevAudioUrl.current = null
    }
    const q = questions[index]
    if (!q?.audio_text) {
      return () => { cancelled = true }
    }
    setAudioUrl(null)
    setAudioLoading(true)
    apiGenerateAudio(q.audio_text)
      .then(({ audio_base64 }) => {
        if (cancelled) return
        const url = base64ToAudioUrl(audio_base64)
        prevAudioUrl.current = url
        setAudioUrl(url)
      })
      .catch(() => {
        if (!cancelled) setError('音声の生成に失敗しました')
      })
      .finally(() => {
        if (!cancelled) setAudioLoading(false)
      })
    return () => {
      cancelled = true
      if (prevAudioUrl.current) {
        URL.revokeObjectURL(prevAudioUrl.current)
        prevAudioUrl.current = null
      }
    }
  }, [index, questions])

  const endSession = async (pomodoro = false) => {
    if (!sessionId) return
    const duration = Math.round((Date.now() - startRef.current) / 1000)
    await apiEndSession(sessionId, {
      duration_seconds: duration,
      questions_attempted: index,
      correct_count: correctCount,
      pomodoro_completed: pomodoro,
    }).catch(() => {})
    setDone(true)
  }

  const handleSelect = async (choiceIndex: number) => {
    if (revealed || !sessionId || !questions[index]) return
    setSelected(choiceIndex)
    const content = questions[index].content as ListeningContent
    const isCorrect = choiceIndex === content.answer
    if (isCorrect) setCorrectCount((c) => c + 1)
    const timeSpent = Math.round((Date.now() - questionStartRef.current) / 1000)
    await apiRecordAttempt(sessionId, {
      question_id: questions[index].id,
      skill: 'listening',
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

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-green-50">
        <div className="text-green-400 text-sm">問題を読み込み中...</div>
      </div>
    )
  }

  if (error) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-green-50 gap-4">
        <p className="text-red-500 text-sm">{error}</p>
        <button onClick={() => router.push('/home')} className="text-indigo-600 underline text-sm">
          ホームへ
        </button>
      </main>
    )
  }

  if (done || questions.length === 0) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-green-50 gap-5">
        <div className="text-5xl">🎧</div>
        <h2 className="text-xl font-bold text-gray-700">
          {questions.length === 0 ? '問題がありません' : 'リスニング完了！'}
        </h2>
        {questions.length > 0 && (
          <p className="text-gray-500 text-sm">{questions.length}問中 {correctCount}問正解</p>
        )}
        <button onClick={() => router.push('/home')} className="bg-indigo-600 text-white px-8 py-3 rounded-xl font-bold">
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
      <PomodoroTimer onBreak={() => { setBreakDialog(true); endSession(true) }} />

      {breakDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-40">
          <div className="bg-white rounded-2xl p-6 max-w-xs mx-4 text-center">
            <div className="text-4xl mb-3">⏰</div>
            <h3 className="font-bold text-gray-800 mb-2">25分経過！</h3>
            <p className="text-gray-500 text-sm mb-4">休憩しましょう</p>
            <button onClick={() => router.push('/home')} className="w-full bg-indigo-600 text-white py-2.5 rounded-xl font-bold">
              ホームへ
            </button>
          </div>
        </div>
      )}

      <div className="bg-white px-4 pt-4 pb-3 shadow-sm">
        <div className="max-w-sm mx-auto">
          <div className="flex justify-between text-xs text-gray-400 mb-1.5">
            <span>リスニング</span>
            <span>{index + 1} / {questions.length}</span>
          </div>
          <div className="w-full bg-gray-100 rounded-full h-2">
            <div className="bg-green-500 h-2 rounded-full transition-all duration-300" style={{ width: `${progress}%` }} />
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="max-w-sm mx-auto space-y-3">
          <div className="bg-white rounded-2xl p-5 shadow-sm text-center">
            {audioLoading ? (
              <p className="text-gray-400 text-sm">音声を生成中...</p>
            ) : audioUrl ? (
              <audio controls src={audioUrl} className="w-full" />
            ) : (
              <p className="text-gray-400 text-sm">音声なし</p>
            )}
          </div>

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
                cls = 'bg-green-100 border-green-400'
              }
              return (
                <button
                  key={i}
                  onClick={() => handleSelect(i)}
                  disabled={revealed}
                  className={`w-full ${cls} border-2 rounded-xl px-4 py-3 text-sm text-left disabled:cursor-default`}
                >
                  {choice}
                </button>
              )
            })}
          </div>

          {revealed && (
            <div className="bg-green-50 rounded-xl p-4">
              <p className="text-xs text-green-500 mb-1">解説</p>
              <p className="text-sm text-green-800">{content.explanation}</p>
            </div>
          )}

          {revealed && (
            <button onClick={handleNext} className="w-full bg-indigo-600 text-white py-3 rounded-xl font-bold">
              {index + 1 >= questions.length ? '完了' : '次の問題へ'}
            </button>
          )}
        </div>
      </div>

      <div className="p-4 text-center">
        <button onClick={() => router.push('/home')} className="text-sm text-gray-400 underline">
          ホームに戻る
        </button>
      </div>
    </main>
  )
}
