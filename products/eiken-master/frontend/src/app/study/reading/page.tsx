'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  apiCreateFlashcard,
  apiEndSession,
  apiExplainJa,
  apiGenerateQuestion,
  apiGetQuestions,
  apiPraise,
  apiRecordAttempt,
  apiStartSession,
  apiVocabHint,
} from '@/lib/api'
import type { ExplainJaResponse, Question, ReadingContent, VocabHintResponse } from '@/lib/types'
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

function speakText(text: string): void {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'en-US'
  utterance.rate = 0.85
  window.speechSynthesis.speak(utterance)
}

interface WordPopup {
  word: string
  hint: VocabHintResponse | null
  loading: boolean
  added: boolean
}

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
  const [praise, setPraise] = useState<string | null>(null)
  const [jaExplain, setJaExplain] = useState<ExplainJaResponse | null>(null)
  const [jaLoading, setJaLoading] = useState(false)
  const [wordPopup, setWordPopup] = useState<WordPopup | null>(null)
  const startRef = useRef<number>(Date.now())
  const questionStartRef = useRef<number>(Date.now())
  const endedRef = useRef(false)
  const sessionIdRef = useRef<string | null>(null)
  const latestRef = useRef({ correctCount: 0, attempted: 0 })
  const wrongOnce = useRef<Set<string>>(new Set())

  useEffect(() => {
    Promise.all([apiStartSession('reading'), apiGetQuestions('reading', 5)])
      .then(async ([session, qs]) => {
        setSessionId(session.id)
        sessionIdRef.current = session.id
        if (qs.length > 0) {
          setQuestions(qs)
        } else {
          const generated = await apiGenerateQuestion('reading')
          setQuestions([generated])
        }
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
    const total = latestRef.current.attempted
    if (total > 0) {
      const pct = latestRef.current.correctCount / total
      apiPraise({ skill: 'reading', is_passing: pct >= 0.6, score_pct: pct, streak: 0 })
        .then((r) => setPraise(r.praise))
        .catch(() => {})
    }
    setDone(true)
  }

  const handleSelect = async (choiceIndex: number) => {
    if (revealed || !sessionId || !questions[index]) return
    setSelected(choiceIndex)
    const content = questions[index].content as ReadingContent
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
      skill: 'reading',
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
      passage: content.passage,
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
      setWordPopup(null)
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

  const handlePassageSelect = useCallback(() => {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed) return
    const word = sel.toString().trim()
    if (word.length === 0 || word.split(' ').length > 4) return
    setWordPopup({ word, hint: null, loading: true, added: false })
    apiVocabHint(word)
      .then((hint) => setWordPopup((prev) => prev ? { ...prev, hint, loading: false } : null))
      .catch(() => setWordPopup((prev) => prev ? { ...prev, loading: false } : null))
  }, [])

  const handleAddToFlashcard = async () => {
    if (!wordPopup?.hint) return
    await apiCreateFlashcard(wordPopup.word, wordPopup.hint.meaning).catch(() => {})
    setWordPopup((prev) => prev ? { ...prev, added: true } : null)
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-blue-50">
        <p className="text-blue-400 text-base">問題を読み込み中...</p>
      </div>
    )
  }

  if (error) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-blue-50 gap-4 px-4">
        <p className="text-red-500 text-base">{error}</p>
        <button onClick={() => router.push('/home')} className="text-indigo-600 underline text-base">ホームへ</button>
      </main>
    )
  }

  if (done || questions.length === 0) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-blue-50 gap-5 px-4">
        <div className="text-6xl">📖</div>
        <h2 className="text-2xl font-bold text-gray-700">
          {questions.length === 0 ? '問題がありません' : 'リーディング完了！'}
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
  const content = q.content as ReadingContent
  const progress = ((index + 1) / questions.length) * 100

  return (
    <main className="min-h-screen bg-blue-50 flex flex-col">
      <PomodoroTimer onBreak={handleBreak} />

      {/* Word popup */}
      {wordPopup && (
        <div className="fixed inset-0 z-50 flex items-end justify-center p-4" onClick={() => setWordPopup(null)}>
          <div className="bg-white rounded-3xl shadow-2xl p-6 max-w-sm w-full" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-4">
              <p className="text-lg font-black text-indigo-700">「{wordPopup.word}」</p>
              <button onClick={() => setWordPopup(null)} className="text-gray-400 text-xl w-8 h-8 flex items-center justify-center">✕</button>
            </div>
            {wordPopup.loading ? (
              <p className="text-gray-400 text-base">調べています...</p>
            ) : wordPopup.hint ? (
              <div className="space-y-3">
                {wordPopup.hint.reading && (
                  <p className="text-sm text-gray-500 font-bold">{wordPopup.hint.reading}</p>
                )}
                <p className="text-xl font-black text-gray-800">{wordPopup.hint.meaning}</p>
                {wordPopup.hint.example && (
                  <p className="text-sm text-gray-500 italic leading-relaxed">{wordPopup.hint.example}</p>
                )}
                <button
                  onClick={handleAddToFlashcard}
                  disabled={wordPopup.added}
                  className={`w-full py-3 rounded-xl font-bold text-sm transition-colors ${
                    wordPopup.added
                      ? 'bg-green-100 text-green-600'
                      : 'bg-indigo-600 text-white hover:bg-indigo-700'
                  }`}
                >
                  {wordPopup.added ? '✓ 単語カードに追加しました' : '🃏 単語カードに追加する'}
                </button>
              </div>
            ) : (
              <p className="text-gray-400 text-base">意味を取得できませんでした</p>
            )}
          </div>
        </div>
      )}

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
          <div className="flex justify-between items-center text-sm text-gray-400 mb-2">
            <span className="font-bold text-blue-600">📖 リーディング</span>
            <div className="flex items-center gap-3">
              {q.difficulty != null && (
                <div className="flex items-center gap-1">
                  <span className="text-[10px] text-gray-400">難易度</span>
                  <div className="flex gap-0.5">
                    {[1,2,3,4,5].map((s) => (
                      <div key={s} className={`w-2 h-2 rounded-full ${s <= Math.round(q.difficulty * 5) ? 'bg-blue-400' : 'bg-gray-200'}`} />
                    ))}
                  </div>
                </div>
              )}
              <span className="font-bold">{index + 1} / {questions.length}</span>
            </div>
          </div>
          <div className="w-full bg-gray-100 rounded-full h-2.5">
            <div className="bg-blue-500 h-2.5 rounded-full transition-all duration-300" style={{ width: `${progress}%` }} />
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="max-w-lg mx-auto space-y-4">

          {/* Passage */}
          {content.passage && (
            <div className="bg-white rounded-2xl p-5 shadow-sm">
              <p className="text-xs text-blue-500 font-black uppercase tracking-wider mb-3">英文パッセージ</p>
              <p
                className="text-base text-gray-700 leading-relaxed select-text"
                onMouseUp={handlePassageSelect}
                onTouchEnd={handlePassageSelect}
              >
                {content.passage}
              </p>
              <p className="text-xs text-gray-400 mt-3">💡 わからない単語を選択すると意味を調べられます</p>
              {revealed && jaExplain?.passage_ja && (
                <div className="mt-3 pt-3 border-t border-blue-100">
                  <p className="text-xs text-blue-500 font-black mb-2">🇯🇵 日本語訳</p>
                  <p className="text-sm text-gray-600 leading-relaxed">{jaExplain.passage_ja}</p>
                </div>
              )}
            </div>
          )}

          {/* Question */}
          <div className="bg-white rounded-2xl p-5 shadow-sm">
            <span className="inline-block bg-blue-500 text-white text-xs font-black px-3 py-1 rounded-full mb-3">
              問題
            </span>
            <p className="text-lg font-bold text-gray-800 leading-snug">{content.question}</p>
            {revealed && jaExplain?.question_ja && (
              <p className="text-sm text-blue-600 mt-2 pt-2 border-t border-blue-100 leading-relaxed">
                🇯🇵 {jaExplain.question_ja}
              </p>
            )}
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
                cls = 'bg-blue-50 border-blue-400 text-blue-800'
                labelCls = 'bg-blue-500 text-white'
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
                  <span className="leading-snug flex-1">
                    <span className="text-base block">{choice}</span>
                    {revealed && jaExplain?.choices_ja[i] && (
                      <span className="text-sm text-gray-500 font-normal mt-0.5 block">
                        {jaExplain.choices_ja[i]}
                      </span>
                    )}
                  </span>
                  {icon && (
                    <span className={`text-2xl font-black shrink-0 ${i === content.answer ? 'text-green-500' : 'text-red-500'}`}>
                      {icon}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          {/* Explanation section */}
          {revealed && (
            <>
              {/* English explanation */}
              <div className="bg-indigo-50 rounded-2xl p-5 border-l-4 border-indigo-400">
                <div className="flex justify-between items-center mb-2">
                  <p className="text-xs text-indigo-500 font-black uppercase tracking-wider">解説（英語）</p>
                  <button
                    onClick={() => speakText(content.explanation)}
                    className="text-indigo-400 hover:text-indigo-600 text-lg p-1"
                    aria-label="音声で読む"
                  >
                    🔊
                  </button>
                </div>
                <p className="text-base text-indigo-800 leading-relaxed">{content.explanation}</p>
              </div>

              {/* Japanese explanation */}
              {jaLoading ? (
                <div className="bg-sky-50 rounded-2xl p-5 flex items-center gap-3">
                  <span className="text-sky-400 text-xl animate-spin">◌</span>
                  <p className="text-sky-500 text-base">日本語の解説を取得中...</p>
                </div>
              ) : jaExplain ? (
                <div className="bg-sky-50 rounded-2xl p-5 border-l-4 border-sky-400 space-y-3">
                  <p className="text-xs text-sky-600 font-black uppercase tracking-wider">🇯🇵 日本語解説</p>
                  <div className="bg-white rounded-xl px-4 py-3 flex items-center gap-3">
                    <span className="text-2xl">✅</span>
                    <div>
                      <p className="text-xs text-gray-400 mb-0.5">正解</p>
                      <p className="text-base font-black text-gray-800">{jaExplain.answer_ja}</p>
                    </div>
                  </div>
                  <p className="text-sm text-sky-900 leading-relaxed whitespace-pre-line">{jaExplain.explanation_ja}</p>
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
