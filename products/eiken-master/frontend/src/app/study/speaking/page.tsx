'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  apiEndSession,
  apiGenerateQuestion,
  apiGetQuestions,
  apiPraise,
  apiRecordAttempt,
  apiScoreSpeaking,
  apiStartSession,
} from '@/lib/api'
import type { Question, SpeakingContent, SpeakingScore } from '@/lib/types'
import PomodoroTimer from '@/components/PomodoroTimer'
import Mascot from '@/components/Mascot'

export default function SpeakingPage() {
  const router = useRouter()
  const [question, setQuestion] = useState<Question | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [phase, setPhase] = useState<'prep' | 'recording' | 'processing' | 'result'>('prep')
  const [score, setScore] = useState<SpeakingScore | null>(null)
  const [praise, setPraise] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [prepCountdown, setPrepCountdown] = useState(30)
  const [recCountdown, setRecCountdown] = useState(0)
  const [breakDialog, setBreakDialog] = useState(false)
  const startRef = useRef<number>(Date.now())
  const mountedRef = useRef(true)
  const endedRef = useRef(false)
  const sessionIdRef = useRef<string | null>(null)
  const handleBreak = useCallback(() => setBreakDialog(true), [])

  const handleGoHome = useCallback(() => {
    if (!endedRef.current && sessionIdRef.current) {
      endedRef.current = true
      const duration = Math.round((Date.now() - startRef.current) / 1000)
      apiEndSession(sessionIdRef.current, {
        duration_seconds: duration,
        questions_attempted: 0,
        correct_count: 0,
        pomodoro_completed: false,
      }).catch(() => {})
    }
    router.push('/home')
  }, [router])
  const mimeTypeRef = useRef<string>('')
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const prepTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const recTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    Promise.all([apiStartSession('speaking'), apiGetQuestions('speaking', 1)])
      .then(async ([session, qs]) => {
        setSessionId(session.id)
        sessionIdRef.current = session.id
        if (qs.length > 0) {
          setQuestion(qs[0])
        } else {
          const generated = await apiGenerateQuestion('speaking')
          setQuestion(generated)
        }
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
    return () => {
      mountedRef.current = false
      if (prepTimerRef.current) clearInterval(prepTimerRef.current)
      if (recTimerRef.current) clearInterval(recTimerRef.current)
      mediaRecorderRef.current?.stop()
      if (!endedRef.current && sessionIdRef.current) {
        const duration = Math.round((Date.now() - startRef.current) / 1000)
        apiEndSession(sessionIdRef.current, {
          duration_seconds: duration,
          questions_attempted: 0,
          correct_count: 0,
          pomodoro_completed: false,
        }).catch(() => {})
      }
    }
  }, [])

  const startPrep = () => {
    setPrepCountdown(30)
    prepTimerRef.current = setInterval(() => {
      setPrepCountdown((c) => {
        if (c <= 1) {
          clearInterval(prepTimerRef.current!)
          return 0
        }
        return c - 1
      })
    }, 1000)
  }

  const startRecording = async () => {
    if (prepTimerRef.current) clearInterval(prepTimerRef.current)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : MediaRecorder.isTypeSupported('audio/mp4')
        ? 'audio/mp4'
        : ''
      mimeTypeRef.current = mimeType
      const mr = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
      chunksRef.current = []
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      mr.onstop = () => {
        stream.getTracks().forEach((t) => t.stop())
        submitRecording()
      }
      mr.start()
      mediaRecorderRef.current = mr
      const content = question?.content as SpeakingContent
      const limit = content?.time_limit_seconds ?? 60
      setRecCountdown(limit)
      setPhase('recording')
      recTimerRef.current = setInterval(() => {
        setRecCountdown((c) => {
          if (c <= 1) {
            clearInterval(recTimerRef.current!)
            mediaRecorderRef.current?.stop()
            return 0
          }
          return c - 1
        })
      }, 1000)
    } catch {
      setError('マイクへのアクセスが許可されていません')
    }
  }

  const stopRecording = () => {
    if (recTimerRef.current) clearInterval(recTimerRef.current)
    mediaRecorderRef.current?.stop()
  }

  const submitRecording = async () => {
    if (!question || !sessionId) return
    if (!mountedRef.current) return
    setPhase('processing')
    const audioBlob = new Blob(chunksRef.current, { type: mimeTypeRef.current || 'audio/webm' })
    const content = question.content as SpeakingContent
    try {
      const result = await apiScoreSpeaking(
        sessionId,
        question.id,
        content.topic,
        content.speaking_points,
        audioBlob
      )
      setScore(result)
      if (!mountedRef.current) return
      await apiRecordAttempt(sessionId, {
        question_id: question.id,
        skill: 'speaking',
        user_answer: result.transcript,
        is_correct: result.is_passing,
      }).catch(() => {})
      endedRef.current = true
      const duration = Math.round((Date.now() - startRef.current) / 1000)
      await apiEndSession(sessionId, {
        duration_seconds: duration,
        questions_attempted: 1,
        correct_count: result.is_passing ? 1 : 0,
      }).catch(() => {})
      apiPraise({ skill: 'speaking', is_passing: result.is_passing, score_pct: result.score / result.max_score, streak: 0 })
        .then((r) => setPraise(r.praise))
        .catch(() => {})
      setPhase('result')
    } catch (err) {
      if (!mountedRef.current) return
      setError(err instanceof Error ? err.message : '採点に失敗しました')
      setPhase('prep')
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-rose-50">
        <div className="text-rose-400 text-sm">問題を読み込み中...</div>
      </div>
    )
  }

  if (error && phase !== 'recording') {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-rose-50 gap-4">
        <p className="text-red-500 text-sm">{error}</p>
        <button onClick={() => router.push('/home')} className="text-indigo-600 underline text-sm">
          ホームへ
        </button>
      </main>
    )
  }

  if (!question) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-rose-50 gap-5">
        <p className="text-gray-500 text-sm">スピーキング問題がありません</p>
        <button onClick={() => router.push('/home')} className="bg-indigo-600 text-white px-8 py-3 rounded-xl font-bold">
          ホームへ
        </button>
      </main>
    )
  }

  const content = question.content as SpeakingContent

  return (
    <main className="min-h-screen bg-rose-50 flex flex-col">
      <PomodoroTimer onBreak={handleBreak} />

      {breakDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-40">
          <div className="bg-white rounded-2xl p-6 max-w-xs mx-4 text-center">
            <Mascot scene="tired" size={100} className="mx-auto mb-2" />
            <h3 className="font-bold text-gray-800 mb-2">25分経過！</h3>
            <p className="text-gray-500 text-sm mb-4">少し休憩しましょう 🍵</p>
            <button onClick={() => router.push('/home')} className="w-full bg-indigo-600 text-white py-2.5 rounded-xl font-bold">
              ホームへ
            </button>
          </div>
        </div>
      )}

      <div className="bg-white px-4 pt-4 pb-3 shadow-sm">
        <p className="max-w-sm mx-auto text-sm font-semibold text-gray-600">スピーキング</p>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="max-w-sm mx-auto space-y-4">
          <div className="bg-white rounded-2xl p-5 shadow-sm">
            <p className="text-xs text-gray-400 mb-2">トピック</p>
            <p className="text-base font-semibold text-gray-800">{content.topic}</p>
            <div className="mt-3 space-y-1">
              {content.speaking_points.map((pt, i) => (
                <p key={i} className="text-xs text-gray-500">• {pt}</p>
              ))}
            </div>
            <p className="text-xs text-rose-400 mt-2">制限時間: {content.time_limit_seconds}秒</p>
          </div>

          {phase === 'prep' && (
            <div className="text-center space-y-4">
              {prepCountdown > 0 ? (
                <p className="text-gray-500 text-sm">準備時間: {prepCountdown}秒</p>
              ) : null}
              {prepCountdown === 0 ? (
                <button
                  onClick={startRecording}
                  className="w-full bg-rose-500 text-white py-4 rounded-2xl font-bold text-lg"
                >
                  録音開始
                </button>
              ) : prepTimerRef.current ? (
                <button
                  onClick={startRecording}
                  className="w-full bg-rose-500 text-white py-4 rounded-2xl font-bold text-lg"
                >
                  録音開始（スキップ）
                </button>
              ) : (
                <button
                  onClick={startPrep}
                  className="w-full bg-amber-400 text-gray-900 py-4 rounded-2xl font-bold text-lg"
                >
                  準備を始める（30秒）
                </button>
              )}
            </div>
          )}

          {phase === 'recording' && (
            <div className="text-center space-y-4">
              <div className="bg-rose-100 rounded-2xl p-6">
                <div className="text-5xl font-bold text-rose-600">{recCountdown}</div>
                <p className="text-rose-400 text-sm mt-1">録音中...</p>
              </div>
              <button
                onClick={stopRecording}
                className="w-full bg-gray-700 text-white py-3 rounded-xl font-bold"
              >
                録音停止
              </button>
            </div>
          )}

          {phase === 'processing' && (
            <div className="flex items-center gap-3 bg-white rounded-2xl px-4 py-4 shadow-sm">
              <Mascot scene="thinking" size={64} className="shrink-0" />
              <div>
                <p className="font-semibold text-gray-700 text-sm">採点中...</p>
                <p className="text-xs text-gray-400 mt-0.5">AIが丁寧に確認しています</p>
              </div>
            </div>
          )}

          {phase === 'result' && score && (
            <>
              <div className={`rounded-2xl p-4 ${score.is_passing ? 'bg-green-50' : 'bg-amber-50'}`}>
                <div className="flex items-center gap-4">
                  <Mascot scene={score.is_passing ? 'celebrate' : 'cheer'} size={72} className="shrink-0" />
                  <div>
                    <p className={`text-3xl font-bold ${score.is_passing ? 'text-green-700' : 'text-orange-600'}`}>
                      {score.score} / {score.max_score}
                    </p>
                    <p className={`text-sm mt-0.5 ${score.is_passing ? 'text-green-600' : 'text-orange-500'}`}>
                      {score.is_passing ? '合格！すばらしい！' : '次は合格できる！'}
                    </p>
                  </div>
                </div>
              </div>
              <div className="bg-white rounded-2xl p-4 shadow-sm">
                <p className="text-xs text-gray-400 mb-1">文字起こし</p>
                <p className="text-sm text-gray-700 italic">"{score.transcript}"</p>
              </div>

              <div className="bg-white rounded-2xl p-4 shadow-sm">
                <p className="text-xs text-gray-400 mb-2">フィードバック</p>
                <p className="text-sm text-gray-700">{score.feedback}</p>
              </div>

              <div className="bg-white rounded-2xl p-4 shadow-sm space-y-3">
                <p className="text-xs text-gray-400">採点詳細</p>
                {Object.entries(score.criteria).map(([key, c]) => (
                  <div key={key}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-gray-600 capitalize">{key}</span>
                      <span className="font-bold text-gray-700">{c.score} / {c.max}</span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-1.5">
                      <div
                        className="bg-rose-400 h-1.5 rounded-full"
                        style={{ width: `${(c.score / c.max) * 100}%` }}
                      />
                    </div>
                    <p className="text-xs text-gray-500 mt-1">{c.comment}</p>
                  </div>
                ))}
              </div>

              <div className="bg-indigo-50 border border-indigo-200 rounded-2xl p-4">
                <p className="text-xs font-bold text-indigo-500 mb-2">💡 模範スピーチのポイント</p>
                <p className="text-sm font-semibold text-indigo-900 mb-2">{content.topic}</p>
                <ul className="space-y-1">
                  {content.speaking_points.map((pt, i) => (
                    <li key={i} className="text-sm text-indigo-700 flex gap-2">
                      <span className="text-indigo-400 shrink-0">{i + 1}.</span>
                      <span>{pt}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {praise && (
                <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 flex gap-3 items-start">
                  <span className="text-xl">🌟</span>
                  <p className="text-sm text-amber-800 leading-relaxed">{praise}</p>
                </div>
              )}

              <button onClick={() => router.push('/home')} className="w-full bg-indigo-600 text-white py-3 rounded-xl font-bold">
                ホームへ
              </button>
            </>
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
