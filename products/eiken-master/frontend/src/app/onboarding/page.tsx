'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiUpdateMe } from '@/lib/api'
import { useAuth } from '@/providers/AuthProvider'

export default function OnboardingPage() {
  const router = useRouter()
  const { user, setUser } = useAuth()
  const [examDate, setExamDate] = useState('')
  const [loading, setLoading] = useState(false)

  const gradeLabel = user?.grade === 'pre2' ? '準2級' : '2級'
  const todayStr = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Tokyo' })

  const handleFinish = async () => {
    setLoading(true)
    try {
      const updated = await apiUpdateMe({ exam_date: examDate || null })
      setUser(updated)
    } catch (err) {
      console.error('onboarding update failed:', err)
    } finally {
      setLoading(false)
      router.replace('/home')
    }
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center bg-indigo-50 px-6">
      <div className="text-5xl mb-4">🎯</div>
      <h1 className="text-2xl font-bold text-indigo-700 mb-1">試験日を設定しよう</h1>
      <p className="text-gray-500 text-sm mb-1 text-center">
        目標: 英検 <span className="font-semibold text-indigo-600">{gradeLabel}</span>
      </p>
      <p className="text-gray-400 text-xs mb-8 text-center">
        試験日を入れると残り日数と合格確率を表示します
      </p>
      <input
        type="date"
        value={examDate}
        onChange={(e) => setExamDate(e.target.value)}
        min={todayStr}
        className="border-2 border-gray-200 focus:border-indigo-400 outline-none rounded-xl px-4 py-3 text-lg mb-6 text-center w-full max-w-xs"
      />
      <button
        onClick={handleFinish}
        disabled={!examDate || loading}
        className="w-full max-w-xs bg-indigo-600 text-white py-3.5 rounded-xl font-bold text-base disabled:opacity-50 active:bg-indigo-700"
      >
        {loading ? '保存中...' : 'スタート！'}
      </button>
      <button
        onClick={() => router.replace('/home')}
        className="mt-4 text-sm text-gray-400 underline"
      >
        あとで設定する
      </button>
    </main>
  )
}
