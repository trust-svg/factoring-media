'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiUpdateMe } from '@/lib/api'
import { useAuth } from '@/providers/AuthProvider'
import type { Grade } from '@/lib/types'

type Step = 'grade' | 'exam_date'

export default function OnboardingPage() {
  const router = useRouter()
  const { setUser } = useAuth()
  const [step, setStep] = useState<Step>('grade')
  const [grade, setGrade] = useState<Grade>('pre2')
  const [examDate, setExamDate] = useState('')
  const [loading, setLoading] = useState(false)

  const handleGradeSelect = (g: Grade) => {
    setGrade(g)
    setStep('exam_date')
  }

  const handleFinish = async () => {
    setLoading(true)
    try {
      const updated = await apiUpdateMe({
        grade,
        exam_date: examDate || null,
      })
      setUser(updated)
    } catch {
      // ignore — go to home anyway
    } finally {
      setLoading(false)
      router.replace('/home')
    }
  }

  const todayStr = new Date().toISOString().split('T')[0]

  if (step === 'grade') {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-indigo-50 px-6">
        <h1 className="text-2xl font-bold text-indigo-700 mb-2">英検マスター</h1>
        <p className="text-gray-500 mb-8 text-center">
          目指す級を選んでください
        </p>
        <div className="flex flex-col gap-4 w-full max-w-xs">
          <button
            onClick={() => handleGradeSelect('pre2')}
            className="bg-white border-2 border-indigo-200 rounded-2xl p-6 text-center shadow-sm hover:border-indigo-500 transition-colors"
          >
            <div className="text-4xl font-bold text-indigo-600">準2級</div>
            <div className="text-sm text-gray-400 mt-1">高校入試レベル</div>
          </button>
          <button
            onClick={() => handleGradeSelect('2')}
            className="bg-white border-2 border-emerald-200 rounded-2xl p-6 text-center shadow-sm hover:border-emerald-500 transition-colors"
          >
            <div className="text-4xl font-bold text-emerald-600">2級</div>
            <div className="text-sm text-gray-400 mt-1">高校卒業レベル</div>
          </button>
        </div>
      </main>
    )
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center bg-indigo-50 px-6">
      <h1 className="text-2xl font-bold text-indigo-700 mb-2">試験日を設定</h1>
      <p className="text-gray-500 mb-6 text-center">
        AIがスケジュールを自動で作ります
      </p>
      <input
        type="date"
        value={examDate}
        onChange={(e) => setExamDate(e.target.value)}
        min={todayStr}
        className="border border-gray-300 rounded-xl px-4 py-3 text-lg mb-6 text-center"
      />
      <button
        onClick={handleFinish}
        disabled={!examDate || loading}
        className="bg-indigo-600 text-white px-10 py-3 rounded-xl font-bold disabled:opacity-50 active:bg-indigo-700"
      >
        {loading ? '保存中...' : 'スタート！'}
      </button>
      <button
        onClick={() => router.replace('/home')}
        className="mt-4 text-sm text-gray-400 underline"
      >
        スキップ
      </button>
    </main>
  )
}
