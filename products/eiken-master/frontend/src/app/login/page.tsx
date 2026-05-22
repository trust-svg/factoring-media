'use client'

import { useState, FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { apiLogin } from '@/lib/api'
import { saveToken } from '@/lib/auth'

export default function LoginPage() {
  const router = useRouter()
  const [username, setUsername] = useState('')
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { access_token } = await apiLogin(username.trim(), pin)
      // Clear any previous user's local state before saving new token
      ;['eiken-notify-sent'].forEach((k) => localStorage.removeItem(k))
      saveToken(access_token)
      window.location.href = '/home'
    } catch (err) {
      setError(err instanceof Error ? err.message : 'ログインに失敗しました')
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
        <p className="text-center text-gray-400 text-sm mb-8">
          ユーザー名と PIN でログイン
        </p>

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
              autoComplete="current-password"
              required
              className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm tracking-widest text-center focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
          </div>

          {error && (
            <p className="text-red-500 text-sm text-center">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading || pin.length !== 4 || username.length === 0}
            className="w-full bg-indigo-600 text-white py-2.5 rounded-xl font-semibold text-sm disabled:opacity-50 active:bg-indigo-700"
          >
            {loading ? 'ログイン中...' : 'ログイン'}
          </button>
        </form>

        <p className="text-center text-sm text-gray-400 mt-6">
          はじめての方は{' '}
          <button
            onClick={() => router.push('/register')}
            className="text-indigo-600 font-medium underline"
          >
            アカウント作成
          </button>
        </p>
      </div>
    </main>
  )
}
