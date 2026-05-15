'use client'

import { useRouter } from 'next/navigation'
import { useAuth } from '@/providers/AuthProvider'
import type { Skill } from '@/lib/types'

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
  return Math.ceil(ms / 86_400_000)
}

export default function HomePage() {
  const { user, loading, logout } = useAuth()
  const router = useRouter()

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
          <button
            onClick={logout}
            className="text-indigo-200 text-sm px-3 py-1 rounded-lg hover:bg-indigo-600"
          >
            ログアウト
          </button>
        </div>
      </header>

      <div className="max-w-lg mx-auto px-4 py-6 space-y-5">
        {/* Exam countdown */}
        {days !== null && (
          <div className="bg-white rounded-2xl shadow-sm p-5 text-center">
            <p className="text-gray-400 text-sm mb-1">試験まで</p>
            <p className="text-5xl font-bold text-indigo-700">
              {days}
              <span className="text-2xl font-normal ml-1">日</span>
            </p>
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

        {/* Onboarding shortcut — shown if exam_date is not set */}
        {!user.exam_date && (
          <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 text-center">
            <p className="text-amber-700 text-sm mb-2">試験日が未設定です</p>
            <button
              onClick={() => router.push('/onboarding')}
              className="bg-amber-500 text-white text-sm px-4 py-1.5 rounded-lg font-semibold"
            >
              設定する
            </button>
          </div>
        )}
      </div>
    </main>
  )
}
