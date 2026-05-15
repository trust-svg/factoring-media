'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  apiEndSession,
  apiGetQuestions,
  apiRecordAttempt,
  apiScoreWriting,
  apiStartSession,
} from '@/lib/api'
import type { Question, WritingContent, WritingScore } from '@/lib/types'
import PomodoroTimer from '@/components/PomodoroTimer'

function countWords(text: string): number {
  return text.trim().split(/\s+/).filter((w) => w.length > 0).length
}

export default function WritingPage() {
  const router = useRouter()
  const [question, setQuestion] = useState<Question | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [answer, setAnswer] = useState('')
  const [score, setScore] = useState<WritingScore | null>(null)
  const [loading, setLoading] = useState(true)
  const [scoring, setScoring] = useState(false)
  const [error, setError] = useState('')
  const [breakDialog, setBreakDialog] = useState(false)
  const startRef = useRef<number>(Date.now())

  useEffect(() => {
    Promise.all([apiStartSession('writing'), apiGetQuestions('writing', 1)])
      .then(([session, qs]) => {
        setSessionId(session.id)
        setQuestion(qs[0] ?? null)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const handleSubmit = async () => {
    if (!question || !sessionId || scoring || answer.trim().length === 0) return
    setScoring(true)
    try {
      const result = await apiScoreWriting({
        session_id: sessionId,
        question_id: question.id,
        answer_text: answer,
      })
      setScore(result)
      await apiRecordAttempt(sessionId, {
        question_id: question.id,
        skill: 'writing',
        user_answer: answer,
        is_correct: result.is_passing,
      }).catch(() => {})
      const duration = Math.round((Date.now() - startRef.current) / 1000)
      await apiEndSession(sessionId, {
        duration_seconds: duration,
        questions_attempted: 1,
        correct_count: result.is_passing ? 1 : 0,
      }).catch(() => {})
    } catch (err) {
      setError(err instanceof Error ? err.message : '採点に失敗しました')
    }
    setScoring(false)
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-amber-50">
        <div className="text-amber-400 text-sm">問題を読み込み中...</div>
      </div>
    )
  }

  if (error && !score) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-amber-50 gap-4">
        <p className="text-red-500 text-sm">{error}</p>
        <button onClick={() => router.push('/home')} className="text-indigo-600 underline text-sm">
          ホームへ
        </button>
      </main>
    )
  }

  if (!question) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-amber-50 gap-5">
        <p className="text-gray-500 text-sm">ライティング問題がありません</p>
        <button onClick={() => router.push('/home')} className="bg-indigo-600 text-white px-8 py-3 rounded-xl font-bold">
          ホームへ
        </button>
      </main>
    )
  }

  const content = question.content as WritingContent
  const wordCount = countWords(answer)
  const meetsMinWords = wordCount >= content.min_words

  return (
    <main className="min-h-screen bg-amber-50 flex flex-col">
      <PomodoroTimer onBreak={() => setBreakDialog(true)} />

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
          <p className="text-sm font-semibold text-gray-600">ライティング</p>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="max-w-sm mx-auto space-y-4">
          <div className="bg-white rounded-2xl p-5 shadow-sm">
            <p className="text-xs text-gray-400 mb-2">課題</p>
            <p className="text-sm text-gray-800 leading-relaxed">{content.prompt}</p>
            <p className="text-xs text-amber-500 mt-2">{content.min_words}語以上で書いてください</p>
          </div>

          {!score ? (
            <>
              <textarea
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                disabled={scoring}
                placeholder="ここに英文を書いてください..."
                className="w-full h-48 bg-white rounded-2xl p-4 text-sm border-2 border-gray-200 focus:border-amber-400 focus:outline-none resize-none"
              />
              <div className="flex justify-between items-center px-1">
                <span className={`text-xs ${meetsMinWords ? 'text-green-600' : 'text-gray-400'}`}>
                  {wordCount} / {content.min_words}語
                </span>
                <button
                  onClick={handleSubmit}
                  disabled={scoring || answer.trim().length === 0}
                  className="bg-amber-500 text-white px-6 py-2.5 rounded-xl font-bold text-sm disabled:opacity-50"
                >
                  {scoring ? '採点中...' : '採点する'}
                </button>
              </div>
            </>
          ) : (
            <>
              <div className={`rounded-2xl p-5 ${score.is_passing ? 'bg-green-50' : 'bg-red-50'}`}>
                <p className={`text-3xl font-bold text-center ${score.is_passing ? 'text-green-700' : 'text-red-600'}`}>
                  {score.score} / {score.max_score}
                </p>
                <p className={`text-center text-sm mt-1 ${score.is_passing ? 'text-green-600' : 'text-red-500'}`}>
                  {score.is_passing ? '合格！' : 'もう少し頑張りましょう'}
                </p>
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
                        className="bg-amber-400 h-1.5 rounded-full"
                        style={{ width: `${(c.score / c.max) * 100}%` }}
                      />
                    </div>
                    <p className="text-xs text-gray-500 mt-1">{c.comment}</p>
                  </div>
                ))}
              </div>

              <button onClick={() => router.push('/home')} className="w-full bg-indigo-600 text-white py-3 rounded-xl font-bold">
                ホームへ
              </button>
            </>
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
