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
  apiScoreWriting,
  apiStartSession,
} from '@/lib/api'
import type {
  ListeningContent,
  Question,
  ReadingContent,
  SpeakingContent,
  SpeakingScore,
  WritingContent,
  WritingScore,
} from '@/lib/types'

type ActivePhase = 'reading' | 'listening' | 'writing' | 'speaking'
type Phase = 'intro' | ActivePhase | 'transition' | 'result'

interface SectionResult {
  skill: string
  score_pct: number
  is_passing: boolean
}

const SKILL_LABELS: Record<string, string> = {
  reading: 'リーディング',
  listening: 'リスニング',
  writing: 'ライティング',
  speaking: 'スピーキング',
}
const SKILL_COLORS: Record<string, string> = {
  reading: '#3b82f6',
  listening: '#22c55e',
  writing: '#f59e0b',
  speaking: '#f43f5e',
}
const SKILL_EMOJI: Record<string, string> = {
  reading: '📖',
  listening: '🎧',
  writing: '✍️',
  speaking: '🎤',
}

// ─── Timer Bar ──────────────────────────────────────────────────────────────
function TimerBar({
  totalSeconds,
  onExpire,
  paused = false,
}: {
  totalSeconds: number
  onExpire: () => void
  paused?: boolean
}) {
  const [remaining, setRemaining] = useState(totalSeconds)
  const pausedRef = useRef(paused)
  pausedRef.current = paused
  const expiredRef = useRef(false)
  const onExpireRef = useRef(onExpire)
  onExpireRef.current = onExpire

  useEffect(() => {
    expiredRef.current = false
    setRemaining(totalSeconds)
    const id = setInterval(() => {
      if (pausedRef.current) return
      setRemaining((r) => {
        if (r <= 1) {
          clearInterval(id)
          if (!expiredRef.current) {
            expiredRef.current = true
            setTimeout(() => onExpireRef.current(), 0)
          }
          return 0
        }
        return r - 1
      })
    }, 1000)
    return () => clearInterval(id)
  }, [totalSeconds])

  const pct = totalSeconds > 0 ? (remaining / totalSeconds) * 100 : 0
  const barColor = pct > 50 ? 'bg-green-400' : pct > 20 ? 'bg-amber-400' : 'bg-red-400'
  const m = Math.floor(remaining / 60)
  const s = remaining % 60

  return (
    <div className="bg-white px-4 py-2 border-b border-gray-100">
      <div className="max-w-lg mx-auto flex items-center gap-3">
        <span
          className={`text-sm font-bold tabular-nums w-12 ${
            pct <= 20 ? 'text-red-500' : 'text-gray-700'
          }`}
        >
          {m}:{String(s).padStart(2, '0')}
        </span>
        <div className="flex-1 bg-gray-100 rounded-full h-2">
          <div
            className={`${barColor} h-2 rounded-full transition-all duration-1000`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
    </div>
  )
}

// ─── Reading Section ────────────────────────────────────────────────────────
function ReadingSection({ onDone }: { onDone: (r: SectionResult) => void }) {
  const [questions, setQuestions] = useState<Question[]>([])
  const [index, setIndex] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expired, setExpired] = useState(false)
  const sessionIdRef = useRef<string | null>(null)
  const startRef = useRef(Date.now())
  const endedRef = useRef(false)
  const resultRef = useRef({ correct: 0, total: 0 })

  const finish = useCallback(async () => {
    if (endedRef.current) return
    endedRef.current = true
    if (sessionIdRef.current) {
      await apiEndSession(sessionIdRef.current, {
        duration_seconds: Math.round((Date.now() - startRef.current) / 1000),
        questions_attempted: resultRef.current.total,
        correct_count: resultRef.current.correct,
      }).catch(() => {})
    }
    const { correct, total } = resultRef.current
    const score_pct = total > 0 ? correct / total : 0
    onDone({ skill: 'reading', score_pct, is_passing: score_pct >= 0.6 })
  }, [onDone])

  useEffect(() => {
    Promise.all([apiStartSession('reading'), apiGetQuestions('reading', 5)])
      .then(async ([session, qs]) => {
        sessionIdRef.current = session.id
        const finalQs =
          qs.length > 0 ? qs : [await apiGenerateQuestion('reading')]
        setQuestions(finalQs)
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
    return () => {
      if (!endedRef.current && sessionIdRef.current) {
        endedRef.current = true
        apiEndSession(sessionIdRef.current, {
          duration_seconds: Math.round((Date.now() - startRef.current) / 1000),
          questions_attempted: resultRef.current.total,
          correct_count: resultRef.current.correct,
        }).catch(() => {})
      }
    }
  }, [])

  const handleExpire = useCallback(() => {
    setExpired(true)
    finish()
  }, [finish])

  const handleAnswer = async (ci: number) => {
    if (revealed || expired) return
    setSelected(ci)
    setRevealed(true)
    const q = questions[index]
    const content = q.content as ReadingContent
    const isCorrect = ci === content.answer
    if (isCorrect) resultRef.current.correct++
    resultRef.current.total++
    if (sessionIdRef.current) {
      await apiRecordAttempt(sessionIdRef.current, {
        question_id: q.id,
        skill: 'reading',
        is_correct: isCorrect,
      }).catch(() => {})
    }
  }

  const next = () => {
    if (index + 1 >= questions.length) {
      finish()
    } else {
      setIndex((i) => i + 1)
      setSelected(null)
      setRevealed(false)
    }
  }

  if (loading)
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-gray-400 text-sm">問題を読み込み中...</p>
      </div>
    )
  if (error)
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-red-500 text-sm">{error}</p>
      </div>
    )
  if (questions.length === 0) return null

  const q = questions[index]
  const content = q.content as ReadingContent

  return (
    <>
      <TimerBar key="reading-timer" totalSeconds={600} onExpire={handleExpire} />
      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="max-w-lg mx-auto space-y-4">
          <p className="text-xs text-gray-400 text-right">
            {index + 1} / {questions.length}
          </p>
          {content.passage && (
            <div className="bg-white rounded-2xl p-4 shadow-sm">
              <p className="text-xs text-gray-400 mb-2">英文</p>
              <p className="text-sm text-gray-700 leading-relaxed">{content.passage}</p>
            </div>
          )}
          <div className="bg-white rounded-2xl p-4 shadow-sm">
            <p className="text-sm font-semibold text-gray-800 mb-3">{content.question}</p>
            <div className="space-y-2">
              {content.choices.map((choice, ci) => {
                let cls = 'bg-gray-50 border border-gray-200'
                if (revealed) {
                  if (ci === content.answer) cls = 'bg-green-100 border border-green-400'
                  else if (ci === selected) cls = 'bg-red-100 border border-red-400'
                } else if (ci === selected) cls = 'bg-indigo-50 border border-indigo-300'
                return (
                  <button
                    key={ci}
                    onClick={() => handleAnswer(ci)}
                    disabled={revealed}
                    className={`w-full text-left px-3 py-2.5 rounded-xl text-sm ${cls}`}
                  >
                    {choice}
                  </button>
                )
              })}
            </div>
            {revealed && (
              <div className="mt-3 p-3 bg-gray-50 rounded-xl">
                <p className="text-xs text-gray-500">{content.explanation}</p>
              </div>
            )}
          </div>
          {revealed && (
            <button
              onClick={next}
              className="w-full bg-indigo-600 text-white py-3 rounded-xl font-bold"
            >
              {index + 1 >= questions.length ? '次のセクションへ' : '次の問題'}
            </button>
          )}
        </div>
      </div>
    </>
  )
}

// ─── Listening Section ──────────────────────────────────────────────────────
function speakText(text: string): void {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'en-US'
  utterance.rate = 0.85
  window.speechSynthesis.speak(utterance)
}

function ListeningSection({ onDone }: { onDone: (r: SectionResult) => void }) {
  const [questions, setQuestions] = useState<Question[]>([])
  const [index, setIndex] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expired, setExpired] = useState(false)
  const sessionIdRef = useRef<string | null>(null)
  const startRef = useRef(Date.now())
  const endedRef = useRef(false)
  const resultRef = useRef({ correct: 0, total: 0 })

  const finish = useCallback(async () => {
    if (endedRef.current) return
    endedRef.current = true
    if (sessionIdRef.current) {
      await apiEndSession(sessionIdRef.current, {
        duration_seconds: Math.round((Date.now() - startRef.current) / 1000),
        questions_attempted: resultRef.current.total,
        correct_count: resultRef.current.correct,
      }).catch(() => {})
    }
    const { correct, total } = resultRef.current
    const score_pct = total > 0 ? correct / total : 0
    onDone({ skill: 'listening', score_pct, is_passing: score_pct >= 0.6 })
  }, [onDone])

  useEffect(() => {
    Promise.all([apiStartSession('listening'), apiGetQuestions('listening', 5)])
      .then(async ([session, qs]) => {
        sessionIdRef.current = session.id
        const finalQs =
          qs.length > 0 ? qs : [await apiGenerateQuestion('listening')]
        setQuestions(finalQs)
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
    return () => {
      window.speechSynthesis?.cancel()
      if (!endedRef.current && sessionIdRef.current) {
        endedRef.current = true
        apiEndSession(sessionIdRef.current, {
          duration_seconds: Math.round((Date.now() - startRef.current) / 1000),
          questions_attempted: resultRef.current.total,
          correct_count: resultRef.current.correct,
        }).catch(() => {})
      }
    }
  }, [])

  const handleExpire = useCallback(() => {
    setExpired(true)
    finish()
  }, [finish])

  const handleAnswer = async (ci: number) => {
    if (revealed || expired) return
    setSelected(ci)
    setRevealed(true)
    const q = questions[index]
    const content = q.content as ListeningContent
    const isCorrect = ci === content.answer
    if (isCorrect) resultRef.current.correct++
    resultRef.current.total++
    if (sessionIdRef.current) {
      await apiRecordAttempt(sessionIdRef.current, {
        question_id: q.id,
        skill: 'listening',
        is_correct: isCorrect,
      }).catch(() => {})
    }
  }

  const next = () => {
    window.speechSynthesis?.cancel()
    if (index + 1 >= questions.length) {
      finish()
    } else {
      setIndex((i) => i + 1)
      setSelected(null)
      setRevealed(false)
    }
  }

  if (loading)
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-gray-400 text-sm">問題を読み込み中...</p>
      </div>
    )
  if (error)
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-red-500 text-sm">{error}</p>
      </div>
    )
  if (questions.length === 0) return null

  const q = questions[index]
  const content = q.content as ListeningContent
  const audioText = q.audio_text || content.question

  return (
    <>
      <TimerBar key="listening-timer" totalSeconds={600} onExpire={handleExpire} />
      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="max-w-lg mx-auto space-y-4">
          <p className="text-xs text-gray-400 text-right">
            {index + 1} / {questions.length}
          </p>
          <div className="bg-white rounded-2xl p-6 shadow-sm text-center">
            <p className="text-xs text-gray-400 mb-3">音声を再生してください</p>
            <button
              onClick={() => speakText(audioText)}
              className="w-16 h-16 rounded-full bg-green-500 hover:bg-green-600 active:scale-95 transition-all flex items-center justify-center mx-auto shadow-md"
            >
              <span className="text-white text-2xl ml-1">▶</span>
            </button>
          </div>
          <div className="bg-white rounded-2xl p-4 shadow-sm">
            <p className="text-sm font-semibold text-gray-800 mb-3">{content.question}</p>
            <div className="space-y-2">
              {content.choices.map((choice, ci) => {
                let cls = 'bg-gray-50 border border-gray-200'
                if (revealed) {
                  if (ci === content.answer) cls = 'bg-green-100 border border-green-400'
                  else if (ci === selected) cls = 'bg-red-100 border border-red-400'
                } else if (ci === selected) cls = 'bg-indigo-50 border border-indigo-300'
                return (
                  <button
                    key={ci}
                    onClick={() => handleAnswer(ci)}
                    disabled={revealed}
                    className={`w-full text-left px-3 py-2.5 rounded-xl text-sm ${cls}`}
                  >
                    {choice}
                  </button>
                )
              })}
            </div>
            {revealed && (
              <div className="mt-3 p-3 bg-gray-50 rounded-xl">
                <p className="text-xs text-gray-500">{content.explanation}</p>
              </div>
            )}
          </div>
          {revealed && (
            <button
              onClick={next}
              className="w-full bg-indigo-600 text-white py-3 rounded-xl font-bold"
            >
              {index + 1 >= questions.length ? '次のセクションへ' : '次の問題'}
            </button>
          )}
        </div>
      </div>
    </>
  )
}

// ─── Writing Section ────────────────────────────────────────────────────────
function WritingSection({ onDone }: { onDone: (r: SectionResult) => void }) {
  const [question, setQuestion] = useState<Question | null>(null)
  const [text, setText] = useState('')
  const [score, setScore] = useState<WritingScore | null>(null)
  const [subPhase, setSubPhase] = useState<'write' | 'processing' | 'result'>('write')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const sessionIdRef = useRef<string | null>(null)
  const startRef = useRef(Date.now())
  const endedRef = useRef(false)
  const textRef = useRef('')
  const questionRef = useRef<Question | null>(null)

  useEffect(() => {
    Promise.all([apiStartSession('writing'), apiGetQuestions('writing', 1)])
      .then(async ([session, qs]) => {
        sessionIdRef.current = session.id
        const q = qs.length > 0 ? qs[0] : await apiGenerateQuestion('writing')
        setQuestion(q)
        questionRef.current = q
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
    return () => {
      if (!endedRef.current && sessionIdRef.current) {
        endedRef.current = true
        apiEndSession(sessionIdRef.current, {
          duration_seconds: Math.round((Date.now() - startRef.current) / 1000),
          questions_attempted: 0,
          correct_count: 0,
        }).catch(() => {})
      }
    }
  }, [])

  const submit = useCallback(
    async (overrideText?: string) => {
      const finalText = overrideText ?? textRef.current
      if (endedRef.current) return
      if (!finalText.trim()) {
        endedRef.current = true
        if (sessionIdRef.current) {
          await apiEndSession(sessionIdRef.current, {
            duration_seconds: Math.round((Date.now() - startRef.current) / 1000),
            questions_attempted: 0,
            correct_count: 0,
          }).catch(() => {})
        }
        onDone({ skill: 'writing', score_pct: 0, is_passing: false })
        return
      }
      if (!sessionIdRef.current || !questionRef.current) return
      const sid = sessionIdRef.current
      const q = questionRef.current
      setSubPhase('processing')
      try {
        const result = await apiScoreWriting({
          session_id: sid,
          question_id: q.id,
          answer_text: finalText,
        })
        setScore(result)
        await apiRecordAttempt(sid, {
          question_id: q.id,
          skill: 'writing',
          user_answer: finalText,
          is_correct: result.is_passing,
        }).catch(() => {})
        endedRef.current = true
        await apiEndSession(sid, {
          duration_seconds: Math.round((Date.now() - startRef.current) / 1000),
          questions_attempted: 1,
          correct_count: result.is_passing ? 1 : 0,
        }).catch(() => {})
        setSubPhase('result')
      } catch (e) {
        setError(e instanceof Error ? e.message : '採点失敗')
        setSubPhase('write')
      }
    },
    [onDone],
  )

  const handleExpire = useCallback(() => submit(textRef.current), [submit])

  if (loading)
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-gray-400 text-sm">問題を読み込み中...</p>
      </div>
    )
  if (error && subPhase !== 'processing')
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-red-500 text-sm">{error}</p>
      </div>
    )
  if (!question) return null

  const content = question.content as WritingContent
  const wordCount = text.trim().split(/\s+/).filter(Boolean).length

  return (
    <>
      <TimerBar key="writing-timer" totalSeconds={900} onExpire={handleExpire} />
      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="max-w-lg mx-auto space-y-4">
          <div className="bg-white rounded-2xl p-4 shadow-sm">
            <p className="text-xs text-gray-400 mb-2">問題</p>
            <p className="text-sm font-semibold text-gray-800">{content.prompt}</p>
            <p className="text-xs text-gray-400 mt-2">{content.min_words}語以上で書いてください</p>
          </div>

          {subPhase === 'write' && (
            <>
              <textarea
                value={text}
                onChange={(e) => {
                  setText(e.target.value)
                  textRef.current = e.target.value
                }}
                placeholder="ここに英文を入力してください..."
                rows={9}
                className="w-full bg-white rounded-2xl p-4 shadow-sm text-sm text-gray-800 border border-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-300 resize-none"
              />
              <div className="flex justify-between items-center">
                <p className="text-xs text-gray-400">{wordCount} 語</p>
                {wordCount < content.min_words && (
                  <p className="text-xs text-amber-500">あと {content.min_words - wordCount} 語</p>
                )}
              </div>
              {error && <p className="text-red-500 text-xs">{error}</p>}
              <button
                onClick={() => submit()}
                disabled={wordCount < 10}
                className="w-full bg-amber-500 hover:bg-amber-600 disabled:opacity-40 text-white py-3 rounded-xl font-bold"
              >
                採点する
              </button>
            </>
          )}

          {subPhase === 'processing' && (
            <div className="text-center py-10">
              <p className="text-gray-400 text-sm">採点中...</p>
            </div>
          )}

          {subPhase === 'result' && score && (
            <>
              <div
                className={`rounded-2xl p-5 text-center ${
                  score.is_passing ? 'bg-green-50' : 'bg-red-50'
                }`}
              >
                <p
                  className={`text-3xl font-bold ${
                    score.is_passing ? 'text-green-700' : 'text-red-600'
                  }`}
                >
                  {score.score} / {score.max_score}
                </p>
                <p
                  className={`text-sm mt-1 ${
                    score.is_passing ? 'text-green-600' : 'text-red-500'
                  }`}
                >
                  {score.is_passing ? '合格！' : 'もう少し頑張りましょう'}
                </p>
              </div>
              <div className="bg-white rounded-2xl p-4 shadow-sm">
                <p className="text-xs text-gray-400 mb-2">フィードバック</p>
                <p className="text-sm text-gray-700 leading-relaxed">{score.feedback}</p>
              </div>
              <button
                onClick={() =>
                  onDone({
                    skill: 'writing',
                    score_pct: score.score / score.max_score,
                    is_passing: score.is_passing,
                  })
                }
                className="w-full bg-indigo-600 text-white py-3 rounded-xl font-bold"
              >
                次のセクションへ
              </button>
            </>
          )}
        </div>
      </div>
    </>
  )
}

// ─── Speaking Section ───────────────────────────────────────────────────────
function SpeakingSection({ onDone }: { onDone: (r: SectionResult) => void }) {
  const [question, setQuestion] = useState<Question | null>(null)
  const [recPhase, setRecPhase] = useState<'prep' | 'recording' | 'processing' | 'result'>('prep')
  const [score, setScore] = useState<SpeakingScore | null>(null)
  const [recCountdown, setRecCountdown] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const sessionIdRef = useRef<string | null>(null)
  const startRef = useRef(Date.now())
  const endedRef = useRef(false)
  const mountedRef = useRef(true)
  const mimeTypeRef = useRef('')
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const recTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    Promise.all([apiStartSession('speaking'), apiGetQuestions('speaking', 1)])
      .then(async ([session, qs]) => {
        sessionIdRef.current = session.id
        const q = qs.length > 0 ? qs[0] : await apiGenerateQuestion('speaking')
        setQuestion(q)
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
    return () => {
      mountedRef.current = false
      if (recTimerRef.current) clearInterval(recTimerRef.current)
      mediaRecorderRef.current?.stop()
      if (!endedRef.current && sessionIdRef.current) {
        endedRef.current = true
        apiEndSession(sessionIdRef.current, {
          duration_seconds: Math.round((Date.now() - startRef.current) / 1000),
          questions_attempted: 0,
          correct_count: 0,
        }).catch(() => {})
      }
    }
  }, [])

  const submitRecording = useCallback(async () => {
    if (!question || !sessionIdRef.current || !mountedRef.current) return
    const sid = sessionIdRef.current
    const content = question.content as SpeakingContent
    setRecPhase('processing')
    const audioBlob = new Blob(chunksRef.current, {
      type: mimeTypeRef.current || 'audio/webm',
    })
    try {
      const result = await apiScoreSpeaking(
        sid,
        question.id,
        content.topic,
        content.speaking_points,
        audioBlob,
      )
      if (!mountedRef.current) return
      setScore(result)
      await apiRecordAttempt(sid, {
        question_id: question.id,
        skill: 'speaking',
        user_answer: result.transcript,
        is_correct: result.is_passing,
      }).catch(() => {})
      endedRef.current = true
      await apiEndSession(sid, {
        duration_seconds: Math.round((Date.now() - startRef.current) / 1000),
        questions_attempted: 1,
        correct_count: result.is_passing ? 1 : 0,
      }).catch(() => {})
      setRecPhase('result')
    } catch (e) {
      if (!mountedRef.current) return
      setError(e instanceof Error ? e.message : '採点失敗')
      setRecPhase('prep')
    }
  }, [question])

  const startRecording = async () => {
    if (!question) return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : MediaRecorder.isTypeSupported('audio/mp4')
        ? 'audio/mp4'
        : ''
      mimeTypeRef.current = mimeType
      const mr = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream)
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
      const content = question.content as SpeakingContent
      const limit = content.time_limit_seconds ?? 60
      setRecCountdown(limit)
      setRecPhase('recording')
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

  if (loading)
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-gray-400 text-sm">問題を読み込み中...</p>
      </div>
    )
  if (error && recPhase !== 'recording')
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-red-500 text-sm">{error}</p>
      </div>
    )
  if (!question) return null

  const content = question.content as SpeakingContent

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4">
      <div className="max-w-lg mx-auto space-y-4">
        <div className="bg-white rounded-2xl p-5 shadow-sm">
          <p className="text-xs text-gray-400 mb-2">トピック</p>
          <p className="text-base font-semibold text-gray-800">{content.topic}</p>
          <div className="mt-3 space-y-1">
            {content.speaking_points.map((pt, i) => (
              <p key={i} className="text-xs text-gray-500">
                • {pt}
              </p>
            ))}
          </div>
          <p className="text-xs text-rose-400 mt-2">制限時間: {content.time_limit_seconds}秒</p>
        </div>

        {recPhase === 'prep' && (
          <button
            onClick={startRecording}
            className="w-full bg-rose-500 text-white py-4 rounded-2xl font-bold text-lg"
          >
            録音開始
          </button>
        )}

        {recPhase === 'recording' && (
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

        {recPhase === 'processing' && (
          <div className="text-center py-10">
            <p className="text-gray-400 text-sm">採点中...</p>
          </div>
        )}

        {recPhase === 'result' && score && (
          <>
            <div
              className={`rounded-2xl p-5 text-center ${
                score.is_passing ? 'bg-green-50' : 'bg-red-50'
              }`}
            >
              <p
                className={`text-3xl font-bold ${
                  score.is_passing ? 'text-green-700' : 'text-red-600'
                }`}
              >
                {score.score} / {score.max_score}
              </p>
              <p
                className={`text-sm mt-1 ${
                  score.is_passing ? 'text-green-600' : 'text-red-500'
                }`}
              >
                {score.is_passing ? '合格！' : 'もう少し頑張りましょう'}
              </p>
            </div>
            <div className="bg-white rounded-2xl p-4 shadow-sm">
              <p className="text-xs text-gray-400 mb-1">文字起こし</p>
              <p className="text-sm text-gray-700 italic">&ldquo;{score.transcript}&rdquo;</p>
            </div>
            <div className="bg-white rounded-2xl p-4 shadow-sm">
              <p className="text-xs text-gray-400 mb-2">フィードバック</p>
              <p className="text-sm text-gray-700 leading-relaxed">{score.feedback}</p>
            </div>
            <button
              onClick={() =>
                onDone({
                  skill: 'speaking',
                  score_pct: score.score / score.max_score,
                  is_passing: score.is_passing,
                })
              }
              className="w-full bg-indigo-600 text-white py-3 rounded-xl font-bold"
            >
              結果を見る
            </button>
          </>
        )}
      </div>
    </div>
  )
}

// ─── Section Transition Screen ───────────────────────────────────────────────
function TransitionScreen({
  from,
  to,
  onReady,
}: {
  from: string
  to: ActivePhase
  onReady: () => void
}) {
  const [countdown, setCountdown] = useState(3)

  useEffect(() => {
    const id = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          clearInterval(id)
          setTimeout(onReady, 0)
          return 0
        }
        return c - 1
      })
    }, 1000)
    return () => clearInterval(id)
  }, [onReady])

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-4 gap-6">
      <div className="text-center">
        <div className="text-5xl mb-3">{SKILL_EMOJI[from]}</div>
        <p className="text-green-600 font-bold text-lg">{SKILL_LABELS[from]} 完了！</p>
      </div>
      <div className="w-px h-10 bg-gray-200" />
      <div className="text-center">
        <p className="text-xs text-gray-400 mb-2">次のセクション</p>
        <div className="text-5xl mb-2">{SKILL_EMOJI[to]}</div>
        <p className="text-indigo-700 font-bold text-lg">{SKILL_LABELS[to]}</p>
      </div>
      <div className="mt-2 text-center">
        <p className="text-4xl font-bold text-gray-300 tabular-nums">{countdown}</p>
        <p className="text-xs text-gray-400 mt-1">秒後に自動開始</p>
      </div>
      <button
        onClick={onReady}
        className="bg-indigo-600 text-white px-8 py-3 rounded-xl font-bold"
      >
        今すぐ開始
      </button>
    </div>
  )
}

// ─── Abort Dialog ────────────────────────────────────────────────────────────
function AbortDialog({ onConfirm, onCancel }: { onConfirm: () => void; onCancel: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 px-4">
      <div className="bg-white rounded-2xl p-6 w-full max-w-xs text-center">
        <div className="text-4xl mb-3">⚠️</div>
        <h3 className="font-bold text-gray-800 mb-1">試験を中断しますか？</h3>
        <p className="text-gray-400 text-sm mb-5">
          現在のセクションの記録は破棄されます
        </p>
        <div className="space-y-2">
          <button
            onClick={onConfirm}
            className="w-full bg-red-500 text-white py-2.5 rounded-xl font-bold"
          >
            中断してホームへ
          </button>
          <button
            onClick={onCancel}
            className="w-full bg-gray-100 text-gray-600 py-2.5 rounded-xl font-medium"
          >
            続ける
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Mock Exam Page ─────────────────────────────────────────────────────────
const SECTION_HEADERS: Record<string, string> = {
  reading: '📖 リーディング (10分)',
  listening: '🎧 リスニング (10分)',
  writing: '✍️ ライティング (15分)',
  speaking: '🎤 スピーキング',
}
const NEXT_PHASE: Record<ActivePhase, Phase> = {
  reading: 'listening',
  listening: 'writing',
  writing: 'speaking',
  speaking: 'result',
}

export default function MockExamPage() {
  const router = useRouter()
  const [phase, setPhase] = useState<Phase>('intro')
  const [pendingPhase, setPendingPhase] = useState<ActivePhase | null>(null)
  const [completedSkill, setCompletedSkill] = useState<string>('')
  const [results, setResults] = useState<SectionResult[]>([])
  const [praise, setPraise] = useState<string | null>(null)
  const [showAbort, setShowAbort] = useState(false)

  const advance = useCallback((r: SectionResult) => {
    setResults((prev) => [...prev, r])
    const next = NEXT_PHASE[r.skill as ActivePhase]
    if (next === 'result') {
      setPhase('result')
    } else {
      setCompletedSkill(r.skill)
      setPendingPhase(next as ActivePhase)
      setPhase('transition')
    }
  }, [])

  const startPending = useCallback(() => {
    if (pendingPhase) {
      setPhase(pendingPhase)
      setPendingPhase(null)
    }
  }, [pendingPhase])

  useEffect(() => {
    if (phase === 'result' && results.length > 0) {
      const avg = results.reduce((s, r) => s + r.score_pct, 0) / results.length
      apiPraise({ skill: 'reading', is_passing: avg >= 0.6, score_pct: avg, streak: 0 })
        .then((r) => setPraise(r.praise))
        .catch(() => {})
    }
  }, [phase, results])

  const handleBack = () => {
    if (phase === 'intro' || phase === 'result') {
      router.back()
    } else {
      setShowAbort(true)
    }
  }

  const overallPct =
    results.length > 0
      ? Math.round((results.reduce((s, r) => s + r.score_pct, 0) / results.length) * 100)
      : 0
  const overallPass = overallPct >= 60

  return (
    <main className="min-h-screen bg-slate-50 flex flex-col">
      {/* ③ 中断ダイアログ */}
      {showAbort && (
        <AbortDialog
          onConfirm={() => router.push('/home')}
          onCancel={() => setShowAbort(false)}
        />
      )}

      {/* Header */}
      <div className="bg-white px-4 pt-4 pb-3 shadow-sm flex items-center gap-3">
        <button onClick={handleBack} className="text-gray-400 text-xl px-1">
          ‹
        </button>
        <div>
          <h1 className="font-bold text-gray-800 text-sm">模擬試験</h1>
          {phase !== 'intro' && phase !== 'result' && phase !== 'transition' && (
            <p className="text-xs text-gray-400">{SECTION_HEADERS[phase]}</p>
          )}
        </div>
        {phase !== 'intro' && phase !== 'result' && (
          <div className="ml-auto flex gap-1">
            {(['reading', 'listening', 'writing', 'speaking'] as const).map((s) => {
              const done = results.some((r) => r.skill === s)
              const active = phase === s
              return (
                <div
                  key={s}
                  className={`w-2 h-2 rounded-full ${
                    done ? 'bg-green-400' : active ? 'bg-indigo-400' : 'bg-gray-200'
                  }`}
                />
              )
            })}
          </div>
        )}
      </div>

      {/* Intro */}
      {phase === 'intro' && (
        <div className="flex-1 overflow-y-auto px-4 py-6">
          <div className="max-w-lg mx-auto space-y-5">
            <div className="bg-white rounded-2xl p-6 shadow-sm text-center">
              <div className="text-5xl mb-3">📝</div>
              <h2 className="text-xl font-bold text-gray-800 mb-2">模擬試験</h2>
              <p className="text-sm text-gray-500 leading-relaxed">
                4技能を通して本番形式で練習しましょう
              </p>
            </div>

            <div className="bg-white rounded-2xl p-5 shadow-sm space-y-4">
              <p className="text-xs text-gray-400 font-semibold">試験構成</p>
              {[
                { emoji: '📖', label: 'リーディング', desc: '5問 · 10分', color: 'text-blue-600' },
                { emoji: '🎧', label: 'リスニング', desc: '5問 · 10分', color: 'text-green-600' },
                { emoji: '✍️', label: 'ライティング', desc: '1問 · 15分', color: 'text-amber-600' },
                { emoji: '🎤', label: 'スピーキング', desc: '1問 · 録音', color: 'text-rose-600' },
              ].map(({ emoji, label, desc, color }) => (
                <div key={label} className="flex items-center gap-3">
                  <span className="text-2xl w-8">{emoji}</span>
                  <div>
                    <p className={`text-sm font-semibold ${color}`}>{label}</p>
                    <p className="text-xs text-gray-400">{desc}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4">
              <p className="text-xs text-amber-700 leading-relaxed">
                各セクションに制限時間があります。時間切れになると自動で次のセクションへ進みます。
              </p>
            </div>

            <button
              onClick={() => setPhase('reading')}
              className="w-full bg-indigo-600 text-white py-4 rounded-2xl font-bold text-lg"
            >
              試験を開始する
            </button>
          </div>
        </div>
      )}

      {/* ① セクション間のトランジション */}
      {phase === 'transition' && pendingPhase && (
        <TransitionScreen
          from={completedSkill}
          to={pendingPhase}
          onReady={startPending}
        />
      )}

      {/* Sections */}
      {phase === 'reading' && <ReadingSection key="reading" onDone={advance} />}
      {phase === 'listening' && <ListeningSection key="listening" onDone={advance} />}
      {phase === 'writing' && <WritingSection key="writing" onDone={advance} />}
      {phase === 'speaking' && <SpeakingSection key="speaking" onDone={advance} />}

      {/* Result */}
      {phase === 'result' && (
        <div className="flex-1 overflow-y-auto px-4 py-6">
          <div className="max-w-lg mx-auto space-y-4">
            <div
              className={`rounded-2xl p-6 text-center shadow-sm ${
                overallPass ? 'bg-green-50' : 'bg-red-50'
              }`}
            >
              <p className="text-xs text-gray-400 mb-1">総合スコア</p>
              <p
                className={`text-6xl font-bold ${
                  overallPass ? 'text-green-700' : 'text-red-600'
                }`}
              >
                {overallPct}%
              </p>
              <p
                className={`text-sm mt-2 font-semibold ${
                  overallPass ? 'text-green-600' : 'text-red-500'
                }`}
              >
                {overallPass ? '合格圏内です！' : 'もう少し頑張りましょう！'}
              </p>
            </div>

            <div className="bg-white rounded-2xl p-5 shadow-sm space-y-3">
              <p className="text-xs text-gray-400">スキル別スコア</p>
              {results.map((r) => {
                const pct = Math.round(r.score_pct * 100)
                return (
                  <div key={r.skill}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-gray-600">{SKILL_LABELS[r.skill]}</span>
                      <span
                        className={`font-bold ${
                          r.is_passing ? 'text-green-600' : 'text-red-500'
                        }`}
                      >
                        {pct}%
                      </span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-2">
                      <div
                        className="h-2 rounded-full"
                        style={{
                          width: `${pct}%`,
                          backgroundColor: SKILL_COLORS[r.skill],
                        }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>

            {praise && (
              <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 flex gap-3 items-start">
                <span className="text-2xl">🌟</span>
                <div>
                  <p className="text-xs text-amber-500 mb-1">お疲れ様でした！</p>
                  <p className="text-sm text-amber-800 leading-relaxed">{praise}</p>
                </div>
              </div>
            )}

            <button
              onClick={() => router.push('/home')}
              className="w-full bg-indigo-600 text-white py-3 rounded-xl font-bold"
            >
              ホームへ
            </button>
            <button
              onClick={() => {
                setPhase('intro')
                setResults([])
                setPraise(null)
              }}
              className="w-full bg-gray-100 text-gray-600 py-3 rounded-xl font-medium text-sm"
            >
              もう一度挑戦
            </button>
          </div>
        </div>
      )}
    </main>
  )
}
