'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiGetDueFlashcards, apiReviewFlashcard } from '@/lib/api'
import type { Flashcard } from '@/lib/types'

interface QualityOption {
  q: number
  label: string
  bg: string
}

const QUALITY_OPTIONS: QualityOption[] = [
  { q: 1, label: '全忘れ', bg: 'bg-red-500' },
  { q: 2, label: '誤答', bg: 'bg-orange-400' },
  { q: 3, label: 'ヒント', bg: 'bg-yellow-400 text-gray-800' },
  { q: 4, label: '正解', bg: 'bg-green-500' },
  { q: 5, label: '即答', bg: 'bg-emerald-600' },
]

export default function FlashcardsPage() {
  const router = useRouter()
  const [cards, setCards] = useState<Flashcard[]>([])
  const [index, setIndex] = useState(0)
  const [revealed, setRevealed] = useState(false)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)

  useEffect(() => {
    apiGetDueFlashcards()
      .then(setCards)
      .catch((err) => console.error('Failed to load cards:', err))
      .finally(() => setLoading(false))
  }, [])

  const handleReview = async (quality: number) => {
    if (submitting) return
    setSubmitting(true)
    const card = cards[index]
    try {
      await apiReviewFlashcard(card.id, quality)
    } catch (err) {
      console.error('Review failed:', err)
    }
    if (index + 1 >= cards.length) {
      setDone(true)
    } else {
      setIndex((i) => i + 1)
      setRevealed(false)
    }
    setSubmitting(false)
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-indigo-50">
        <div className="text-indigo-400 text-sm">カードを読み込み中...</div>
      </div>
    )
  }

  if (done || cards.length === 0) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-indigo-50 gap-5">
        <div className="text-6xl">{cards.length === 0 ? '😴' : '🎉'}</div>
        <h2 className="text-xl font-bold text-gray-700">
          {cards.length === 0
            ? '今日の復習カードはありません！'
            : '今日の復習、完了！'}
        </h2>
        {done && (
          <p className="text-gray-400 text-sm">
            {cards.length} 枚のカードを復習しました
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

  const card = cards[index]
  const progress = (index / cards.length) * 100

  return (
    <main className="min-h-screen bg-indigo-50 flex flex-col">
      {/* Progress bar */}
      <div className="bg-white px-4 pt-4 pb-3 shadow-sm">
        <div className="max-w-sm mx-auto">
          <div className="flex justify-between text-xs text-gray-400 mb-1.5">
            <span>フラッシュカード</span>
            <span>{index + 1} / {cards.length}</span>
          </div>
          <div className="w-full bg-gray-100 rounded-full h-2">
            <div
              className="bg-indigo-500 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>

      {/* Card area */}
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-6">
        <div className="w-full max-w-sm space-y-4">
          {/* Front */}
          <div className="bg-white rounded-2xl shadow-sm p-8 text-center">
            <p className="text-xs text-gray-300 uppercase tracking-widest mb-3">英語</p>
            <p className="text-3xl font-bold text-gray-800">{card.front}</p>
          </div>

          {/* Back / Reveal */}
          {revealed ? (
            <>
              <div className="bg-indigo-50 border-2 border-indigo-200 rounded-2xl p-6 text-center">
                <p className="text-xs text-indigo-300 uppercase tracking-widest mb-2">意味</p>
                <p className="text-2xl font-bold text-indigo-700">{card.back}</p>
              </div>

              <p className="text-center text-xs text-gray-400">
                どれくらい覚えていましたか？
              </p>

              <div className="grid grid-cols-5 gap-2">
                {QUALITY_OPTIONS.map(({ q, label, bg }) => (
                  <button
                    key={q}
                    onClick={() => handleReview(q)}
                    disabled={submitting}
                    className={`${bg} text-white rounded-xl py-2.5 text-xs font-bold disabled:opacity-50`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <button
              onClick={() => setRevealed(true)}
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white rounded-2xl py-4 font-bold text-lg transition-colors"
            >
              答えを見る
            </button>
          )}
        </div>
      </div>

      {/* Back nav */}
      <div className="p-4 text-center">
        <button
          onClick={() => router.push('/home')}
          className="text-sm text-gray-400 underline"
        >
          ホームに戻る
        </button>
      </div>
    </main>
  )
}
