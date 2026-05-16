'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiUpdateMe } from '@/lib/api'
import { useAuth } from '@/providers/AuthProvider'

export default function SettingsPage() {
  const router = useRouter()
  const { user, setUser } = useAuth()
  const [examDate, setExamDate] = useState(user?.exam_date ?? '')
  const [dailyGoal, setDailyGoal] = useState(user?.daily_goal_minutes ?? 30)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  if (!user) return null

  const gradeLabel = user.grade === 'pre2' ? '準2級' : '2級'
  const todayStr = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Tokyo' })

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      const updated = await apiUpdateMe({
        exam_date: examDate || null,
        daily_goal_minutes: dailyGoal,
      })
      setUser(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      console.error('settings save failed:', err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="min-h-screen bg-gray-50">
      <div className="bg-white px-4 pt-4 pb-3 shadow-sm flex items-center gap-3">
        <button onClick={() => router.back()} className="text-gray-400 text-xl px-1">‹</button>
        <h1 className="font-bold text-gray-800">設定</h1>
      </div>

      <div className="max-w-sm mx-auto px-4 py-6 space-y-4">
        <div className="bg-white rounded-2xl p-5 shadow-sm">
          <p className="text-xs text-gray-400 mb-1">ユーザー名</p>
          <p className="font-semibold text-gray-800">{user.username}</p>
          <p className="text-xs text-gray-400 mt-3 mb-1">目標</p>
          <p className="font-semibold text-gray-800">英検 {gradeLabel}</p>
        </div>

        <div className="bg-white rounded-2xl p-5 shadow-sm space-y-4">
          <div>
            <label className="text-xs text-gray-400 block mb-1.5">試験日</label>
            <input
              type="date"
              value={examDate}
              onChange={(e) => setExamDate(e.target.value)}
              min={todayStr}
              className="w-full border-2 border-gray-200 focus:border-indigo-400 outline-none rounded-xl px-4 py-2.5 text-base"
            />
          </div>

          <div>
            <label className="text-xs text-gray-400 block mb-1.5">
              1日の目標学習時間: <span className="font-semibold text-gray-700">{dailyGoal}分</span>
            </label>
            <input
              type="range"
              min={10}
              max={120}
              step={5}
              value={dailyGoal}
              onChange={(e) => setDailyGoal(Number(e.target.value))}
              className="w-full accent-indigo-600"
            />
            <div className="flex justify-between text-xs text-gray-400 mt-1">
              <span>10分</span>
              <span>120分</span>
            </div>
          </div>
        </div>

        <button
          onClick={handleSave}
          disabled={saving}
          className="w-full bg-indigo-600 text-white py-3.5 rounded-xl font-bold disabled:opacity-50 active:bg-indigo-700"
        >
          {saving ? '保存中...' : saved ? '保存しました ✓' : '保存する'}
        </button>
      </div>
    </main>
  )
}
