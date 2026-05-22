'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiGenerateAudio, apiGenerateFlashcardExample, apiGetDueFlashcards, apiReviewFlashcard, apiSeedVocab } from '@/lib/api'
import type { Flashcard } from '@/lib/types'
import { useAuth } from '@/providers/AuthProvider'

interface QualityOption {
  q: number
  emoji: string
  label: string
  desc: string
  bg: string
  text: string
}

const QUALITY_OPTIONS: QualityOption[] = [
  { q: 1, emoji: '😭', label: '全然わからない', desc: '見ても思い出せなかった', bg: 'bg-red-500', text: 'text-white' },
  { q: 2, emoji: '😔', label: 'まちがえた', desc: '意味はなんとなく…', bg: 'bg-orange-400', text: 'text-white' },
  { q: 3, emoji: '🤔', label: 'うっすら正解', desc: 'ヒントがあれば思い出せた', bg: 'bg-yellow-400', text: 'text-gray-800' },
  { q: 4, emoji: '😊', label: '正解！', desc: '考えたら思い出せた', bg: 'bg-green-500', text: 'text-white' },
  { q: 5, emoji: '⚡', label: '即答！', desc: 'すぐに答えられた', bg: 'bg-emerald-600', text: 'text-white' },
]

export default function FlashcardsPage() {
  const router = useRouter()
  const { user } = useAuth()
  const [cards, setCards] = useState<Flashcard[]>([])
  const [index, setIndex] = useState(0)
  const [revealed, setRevealed] = useState(false)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState(false)
  const [reviewError, setReviewError] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)
  const [seeding, setSeeding] = useState(false)
  const [seedDone, setSeedDone] = useState(false)
  const [example, setExample] = useState<string | null>(null)
  const [exampleJa, setExampleJa] = useState<string | null>(null)
  const [exampleLoading, setExampleLoading] = useState(false)
  const [audioPlaying, setAudioPlaying] = useState(false)
  const audioCache = useState<Map<string, string>>(() => new Map())[0]

  useEffect(() => {
    apiGetDueFlashcards()
      .then(setCards)
      .catch((err) => {
        console.error('Failed to load cards:', err)
        setFetchError(true)
      })
      .finally(() => setLoading(false))
  }, [])

  const handlePlayWord = async (text: string, cacheKey: string) => {
    if (audioPlaying) return
    setAudioPlaying(true)
    try {
      let url = audioCache.get(cacheKey)
      if (!url) {
        const { audio_base64 } = await apiGenerateAudio(text)
        const bin = atob(audio_base64)
        const bytes = new Uint8Array(bin.length)
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
        url = URL.createObjectURL(new Blob([bytes], { type: 'audio/mpeg' }))
        audioCache.set(cacheKey, url)
      }
      const audio = new Audio(url)
      audio.onended = () => setAudioPlaying(false)
      audio.onerror = () => setAudioPlaying(false)
      audio.play().catch(() => setAudioPlaying(false))
    } catch {
      setAudioPlaying(false)
    }
  }

  const handleReveal = async () => {
    setRevealed(true)
    const card = cards[index]
    if (card.example) {
      setExample(card.example)
      setExampleJa(card.example_ja)
      return
    }
    setExampleLoading(true)
    try {
      const { example: ex, example_ja: exJa } = await apiGenerateFlashcardExample(card.id)
      setExample(ex)
      setExampleJa(exJa ?? null)
      setCards((prev) => prev.map((c, i) => i === index ? { ...c, example: ex, example_ja: exJa ?? null } : c))
    } catch {
      // ignore
    } finally {
      setExampleLoading(false)
    }
  }

  const handleReview = async (quality: number) => {
    if (submitting) return
    setSubmitting(true)
    setReviewError(false)
    const card = cards[index]
    try {
      await apiReviewFlashcard(card.id, quality)
      if (index + 1 >= cards.length) {
        setDone(true)
      } else {
        setIndex((i) => i + 1)
        setRevealed(false)
        setExample(null)
        setExampleJa(null)
        setAudioPlaying(false)
      }
    } catch (err) {
      console.error('Review failed:', err)
      setReviewError(true)
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

  if (fetchError) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-indigo-50 gap-5">
        <div className="text-6xl">⚠️</div>
        <h2 className="text-xl font-bold text-gray-700">読み込みに失敗しました</h2>
        <p className="text-gray-400 text-sm">ネットワーク接続を確認してください</p>
        <button
          onClick={() => router.push('/home')}
          className="bg-indigo-600 text-white px-8 py-3 rounded-xl font-bold"
        >
          ホームへ
        </button>
      </main>
    )
  }

  const handleSeedVocab = async () => {
    if (!user || seeding) return
    setSeeding(true)
    try {
      const result = await apiSeedVocab(user.grade)
      setSeedDone(true)
      if (result.created > 0) {
        const fresh = await apiGetDueFlashcards()
        setCards(fresh)
        setIndex(0)
        setDone(false)
      }
    } catch {
      // silently ignore
    }
    setSeeding(false)
  }

  if (done || cards.length === 0) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-indigo-50 gap-5 px-4">
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
        {cards.length === 0 && !seedDone && (
          <div className="text-center space-y-3">
            <p className="text-gray-400 text-sm">英検レベルの単語リストをインポートして始めよう！</p>
            <button
              onClick={handleSeedVocab}
              disabled={seeding}
              className="bg-indigo-600 text-white px-8 py-3 rounded-xl font-bold text-sm disabled:opacity-50"
            >
              {seeding ? '追加中...' : '📚 英検単語をインポート'}
            </button>
          </div>
        )}
        {seedDone && cards.length === 0 && (
          <p className="text-green-600 text-sm font-bold">✓ 単語を追加しました！明日から復習できます</p>
        )}
        <button
          onClick={() => {
            if (done) sessionStorage.setItem('eiken-skill-done', 'flashcards')
            router.push('/home')
          }}
          className="bg-indigo-600 text-white px-8 py-3 rounded-xl font-bold"
        >
          ホームへ
        </button>
      </main>
    )
  }

  const card = cards[index]
  const progress = ((index + 1) / cards.length) * 100

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
            <button
              onClick={() => handlePlayWord(card.front, `word-${card.id}`)}
              disabled={audioPlaying}
              className="mt-4 inline-flex items-center gap-1.5 text-indigo-400 hover:text-indigo-600 disabled:opacity-40 text-sm font-medium transition-colors"
            >
              <span className="text-lg">{audioPlaying ? '🔊' : '▶'}</span>
              {audioPlaying ? '再生中' : '発音を聴く'}
            </button>
          </div>

          {/* Back / Reveal */}
          {revealed ? (
            <>
              <div className="bg-indigo-50 border-2 border-indigo-200 rounded-2xl p-6 text-center space-y-3">
                <div>
                  <p className="text-xs text-indigo-300 uppercase tracking-widest mb-2">意味</p>
                  <p className="text-2xl font-bold text-indigo-700">{card.back}</p>
                </div>
                <div className="border-t border-indigo-100 pt-3">
                  <p className="text-xs text-indigo-300 uppercase tracking-widest mb-1.5">例文</p>
                  {exampleLoading ? (
                    <p className="text-sm text-indigo-300 italic">生成中...</p>
                  ) : example ? (
                    <div className="space-y-1">
                      <div className="flex items-start gap-2">
                        <p className="text-sm text-indigo-700 italic leading-relaxed flex-1">{example}</p>
                        <button
                          onClick={() => handlePlayWord(example, `ex-${card.id}`)}
                          disabled={audioPlaying}
                          className="shrink-0 text-indigo-300 hover:text-indigo-500 disabled:opacity-40 text-base transition-colors"
                          aria-label="例文を読む"
                        >
                          🔊
                        </button>
                      </div>
                      {exampleJa && (
                        <p className="text-xs text-indigo-400 leading-relaxed">🇯🇵 {exampleJa}</p>
                      )}
                    </div>
                  ) : null}
                </div>
              </div>

              <p className="text-center text-xs font-semibold text-gray-500">
                どれくらい覚えていましたか？
              </p>

              {reviewError && (
                <p className="text-red-500 text-xs text-center">
                  送信に失敗しました。もう一度試してください。
                </p>
              )}

              <div className="space-y-2">
                {QUALITY_OPTIONS.map(({ q, emoji, label, desc, bg, text }) => (
                  <button
                    key={q}
                    onClick={() => handleReview(q)}
                    disabled={submitting}
                    className={`${bg} ${text} rounded-xl px-4 py-3 flex items-center gap-3 w-full text-left disabled:opacity-50 active:scale-95 transition-transform`}
                  >
                    <span className="text-2xl shrink-0">{emoji}</span>
                    <div>
                      <p className="text-sm font-bold leading-tight">{label}</p>
                      <p className="text-xs opacity-80 leading-tight">{desc}</p>
                    </div>
                  </button>
                ))}
              </div>
            </>
          ) : (
            <button
              onClick={handleReveal}
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
