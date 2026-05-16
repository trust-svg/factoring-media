'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiGetProgress } from '@/lib/api'
import { useAuth } from '@/providers/AuthProvider'
import type { ProgressData, Skill } from '@/lib/types'

interface StudyMode {
  skill: Skill
  label: string
  emoji: string
  bg: string
  text: string
}

const STUDY_MODES: StudyMode[] = [
  { skill: 'reading', label: 'リーディング', emoji: '📖', bg: 'bg-blue-100', text: 'text-blue-700' },
  { skill: 'listening', label: 'リスニング', emoji: '🎧', bg: 'bg-green-100', text: 'text-green-700' },
  { skill: 'writing', label: 'ライティング', emoji: '✍️', bg: 'bg-amber-100', text: 'text-amber-700' },
  { skill: 'speaking', label: 'スピーキング', emoji: '🎤', bg: 'bg-rose-100', text: 'text-rose-700' },
]

function daysUntil(dateStr: string | null): number | null {
  if (!dateStr) return null
  const ms = new Date(dateStr).getTime() - Date.now()
  return Math.max(0, Math.ceil(ms / 86_400_000))
}

export default function HomePage() {
  const { user, loading, logout } = useAuth()
  const router = useRouter()
  const [progress, setProgress] = useState<ProgressData | null>(null)

  useEffect(() => {
    if (!loading && user && !user.exam_date) {
      router.replace('/onboarding')
    }
  }, [loading, user, router])

  useEffect(() => {
    if (!loading && user) {
      apiGetProgress().then(setProgress).catch(() => {})
    }
  }, [loading, user])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-indigo-50">
        <div className="text-indigo-400 text-sm">読み込み中...</div>
      </div>
    )
  }

  if (!user) return null

  const days = daysUntil(user.exam_date)
  const gradeLabel = user.grade === 'pre2' ? '準2級' : '2級'

  return (
    <main className="min-h-screen bg-indigo-50">
      {/* Header */}
      <header className="bg-indigo-700 text-white px-4 py-4">
        <div className="max-w-lg mx-auto flex justify-between items-center">
          <div>
            <h1 className="font-bold text-lg leading-tight">英検マスター</h1>
            <p className="text-indigo-200 text-xs mt-0.5">
              {gradeLabel} · {user.username}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => router.push('/settings')}
              className="text-indigo-200 text-xl px-2 py-1 rounded-lg hover:bg-indigo-600"
              aria-label="設定"
            >
              ⚙️
            </button>
            <button
              onClick={logout}
              className="text-indigo-200 text-sm px-3 py-1 rounded-lg hover:bg-indigo-600"
            >
              ログアウト
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-lg mx-auto px-4 py-6 space-y-5">
        {/* Progress card */}
        <button
          onClick={() => router.push('/progress')}
          className="w-full bg-white rounded-2xl shadow-sm p-5 text-left"
        >
          <div className="flex justify-between items-start">
            <div>
              <p className="text-xs text-gray-400 mb-1">合格確率</p>
              {progress?.pass_probability != null ? (
                <p className={`text-4xl font-bold ${progress.pass_probability >= 0.7 ? 'text-green-600' : progress.pass_probability >= 0.5 ? 'text-amber-500' : 'text-red-500'}`}>
                  {Math.round(progress.pass_probability * 100)}%
                </p>
              ) : (
                <p className="text-2xl font-bold text-gray-300">—%</p>
              )}
            </div>
            <div className="text-right">
              {days !== null && (
                <div>
                  <p className="text-xs text-gray-400">試験まで</p>
                  <p className="text-2xl font-bold text-indigo-700">{days}<span className="text-sm font-normal ml-0.5">日</span></p>
                </div>
              )}
              <p className="text-xs text-indigo-400 mt-1">詳細を見る ›</p>
            </div>
          </div>
          {progress?.pass_probability != null && (
            <div className="w-full bg-gray-100 rounded-full h-1.5 mt-3">
              <div
                className={`h-1.5 rounded-full ${progress.pass_probability >= 0.7 ? 'bg-green-500' : progress.pass_probability >= 0.5 ? 'bg-amber-400' : 'bg-red-400'}`}
                style={{ width: `${Math.round(progress.pass_probability * 100)}%` }}
              />
            </div>
          )}
        </button>

        {/* Praise card */}
        {progress?.praise && (
          <div className="bg-amber-50 border border-amber-200 rounded-2xl px-4 py-3 flex gap-3 items-start">
            <span className="text-xl mt-0.5">🌟</span>
            <p className="text-sm text-amber-800 leading-relaxed">{progress.praise}</p>
          </div>
        )}

        {/* AI Advice */}
        {progress?.advice && (
          <div className="bg-indigo-50 border border-indigo-100 rounded-2xl px-4 py-3">
            <p className="text-xs text-indigo-400 mb-1">AIコーチ</p>
            <p className="text-sm text-indigo-800 leading-relaxed">{progress.advice}</p>
          </div>
        )}

        {/* Flashcard CTA */}
        <button
          onClick={() => router.push('/flashcards')}
          className="w-full bg-indigo-600 hover:bg-indigo-700 text-white rounded-2xl shadow-sm p-4 flex items-center gap-4 transition-colors"
        >
          <span className="text-4xl">🃏</span>
          <div className="text-left">
            <div className="font-bold text-base">今日の単語カード</div>
            <div className="text-indigo-200 text-sm">SM-2 間隔反復</div>
          </div>
          <span className="ml-auto text-indigo-300 text-xl">›</span>
        </button>

        {/* Study mode grid */}
        <div>
          <h2 className="font-bold text-gray-600 text-sm mb-3 px-1">学習モード</h2>
          <div className="grid grid-cols-2 gap-3">
            {STUDY_MODES.map(({ skill, label, emoji, bg, text }) => (
              <button
                key={skill}
                onClick={() => router.push(`/study/${skill}`)}
                className={`${bg} ${text} rounded-2xl p-5 text-left shadow-sm hover:opacity-80 transition-opacity`}
              >
                <div className="text-3xl mb-2">{emoji}</div>
                <div className="font-semibold text-sm">{label}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Bottom row: mock exam + vocabulary */}
        <div className="grid grid-cols-2 gap-3">
          <button
            onClick={() => router.push('/mock-exam')}
            className="bg-slate-700 hover:bg-slate-800 text-white rounded-2xl shadow-sm p-4 text-left transition-colors"
          >
            <div className="text-3xl mb-2">📝</div>
            <div className="font-semibold text-sm">模擬試験</div>
            <div className="text-slate-400 text-xs mt-0.5">4技能 · 本番形式</div>
          </button>
          <button
            onClick={() => router.push('/vocabulary')}
            className="bg-violet-600 hover:bg-violet-700 text-white rounded-2xl shadow-sm p-4 text-left transition-colors"
          >
            <div className="text-3xl mb-2">🔗</div>
            <div className="font-semibold text-sm">語彙ネットワーク</div>
            <div className="text-violet-300 text-xs mt-0.5">語根クラスター</div>
          </button>
        </div>

      </div>
    </main>
  )
}
