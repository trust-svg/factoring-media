'use client'

import { useState, FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { apiRegister } from '@/lib/api'
import { saveToken } from '@/lib/auth'
import type { Grade } from '@/lib/types'

export default function RegisterPage() {
  const router = useRouter()
  const [username, setUsername] = useState('')
  const [pin, setPin] = useState('')
  const [grade, setGrade] = useState<Grade>('pre2')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { access_token } = await apiRegister(username.trim(), pin, grade)
      saveToken(access_token)
      router.replace('/onboarding')
    } catch (err) {
      setError(err instanceof Error ? err.message : '登録に失敗しました')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-indigo-50 px-4">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-lg p-8">
        <h1 className="text-2xl font-bold text-center text-indigo-700 mb-1">
          英検マスター
        </h1>
        <p className="text-center text-gray-400 text-sm mb-8">新しいアカウントを作成</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              ユーザー名
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
              className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              PIN（4桁）
            </label>
            <input
              type="password"
              inputMode="numeric"
              maxLength={4}
              value={pin}
              onChange={(e) =>
                setPin(e.target.value.replace(/\D/g, '').slice(0, 4))
              }
              autoComplete="new-password"
              required
              className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm tracking-widest text-center focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              目指す級
            </label>
            <div className="flex gap-3">
              {(['pre2', '2'] as Grade[]).map((g) => (
                <button
                  key={g}
                  type="button"
                  onClick={() => setGrade(g)}
                  className={`flex-1 py-2.5 rounded-xl text-sm font-bold border-2 transition-colors ${
                    grade === g
                      ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
                      : 'border-gray-200 text-gray-500'
                  }`}
                >
                  {g === 'pre2' ? '準2級' : '2級'}
                </button>
              ))}
            </div>
          </div>

          {error && (
            <p className="text-red-500 text-sm text-center">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading || pin.length !== 4 || username.length === 0}
            className="w-full bg-indigo-600 text-white py-2.5 rounded-xl font-semibold text-sm disabled:opacity-50 active:bg-indigo-700"
          >
            {loading ? '作成中...' : 'アカウント作成'}
          </button>
        </form>

        <p className="text-center text-sm text-gray-400 mt-6">
          すでにアカウントがある方は{' '}
          <button
            onClick={() => router.push('/login')}
            className="text-indigo-600 font-medium underline"
          >
            ログイン
          </button>
        </p>
      </div>
    </main>
  )
}
