'use client'

import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiGetVapidPublicKey, apiPushSubscribe, apiPushTest, apiPushUnsubscribe, apiUpdateMe } from '@/lib/api'
import { useAuth } from '@/providers/AuthProvider'

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)))
}

function extractKeys(sub: PushSubscription): { p256dh: string; auth: string } {
  const p256dh = btoa(String.fromCharCode(...new Uint8Array(sub.getKey('p256dh')!)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  const auth = btoa(String.fromCharCode(...new Uint8Array(sub.getKey('auth')!)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return { p256dh, auth }
}

const DAY_LABELS = ['月', '火', '水', '木', '金', '土', '日']
const DEFAULT_TIME = '20:00'

function initSchedule(user: { reminder_schedule: Record<string, string> | null; reminder_days: number[]; reminder_time: string } | null): Record<string, string> {
  if (user?.reminder_schedule && Object.keys(user.reminder_schedule).length > 0) {
    return user.reminder_schedule
  }
  // migrate from old reminder_days + reminder_time
  const sched: Record<string, string> = {}
  const days = user?.reminder_days ?? [0, 1, 2, 3, 4, 5, 6]
  const time = user?.reminder_time ?? DEFAULT_TIME
  days.forEach((d) => { sched[String(d)] = time })
  return sched
}

export default function SettingsPage() {
  const router = useRouter()
  const { user, setUser, logout } = useAuth()
  const [grade, setGrade] = useState<'pre2' | '2'>(user?.grade ?? 'pre2')
  const [examDate, setExamDate] = useState(user?.exam_date ?? '')
  const [dailyGoal, setDailyGoal] = useState(user?.daily_goal_minutes ?? 30)
  // reminder_schedule: key=weekday index string, value=HH:MM time
  const [schedule, setSchedule] = useState<Record<string, string>>(() => initSchedule(user))
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  // Push notification state
  const [notifSupported, setNotifSupported] = useState(false)
  const [notifEnabled, setNotifEnabled] = useState(false)
  const [notifLoading, setNotifLoading] = useState(false)
  const [notifStatus, setNotifStatus] = useState<string | null>(null)

  useEffect(() => {
    if (typeof window === 'undefined') return
    const supported =
      'Notification' in window &&
      'serviceWorker' in navigator &&
      'PushManager' in window
    setNotifSupported(supported)
    if (!supported) return
    navigator.serviceWorker.ready.then((reg) =>
      reg.pushManager.getSubscription().then((sub) => setNotifEnabled(!!sub))
    )
  }, [])

  const enableNotifications = useCallback(async () => {
    setNotifLoading(true)
    setNotifStatus(null)
    try {
      const permission = await Notification.requestPermission()
      if (permission !== 'granted') {
        setNotifStatus('通知が許可されていません。ブラウザの設定を確認してください。')
        return
      }
      const { public_key } = await apiGetVapidPublicKey()
      const reg = await navigator.serviceWorker.ready
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(public_key).buffer as ArrayBuffer,
      })
      const { p256dh, auth } = extractKeys(sub)
      await apiPushSubscribe({ endpoint: sub.endpoint, p256dh, auth })
      setNotifEnabled(true)
      setNotifStatus('通知を有効にしました')
    } catch (err) {
      console.error('push subscribe failed:', err)
      setNotifStatus('通知の設定に失敗しました')
    } finally {
      setNotifLoading(false)
    }
  }, [])

  const disableNotifications = useCallback(async () => {
    setNotifLoading(true)
    setNotifStatus(null)
    try {
      const reg = await navigator.serviceWorker.ready
      const sub = await reg.pushManager.getSubscription()
      if (sub) {
        const { p256dh, auth } = extractKeys(sub)
        await apiPushUnsubscribe({ endpoint: sub.endpoint, p256dh, auth })
        await sub.unsubscribe()
      }
      setNotifEnabled(false)
      setNotifStatus('通知を無効にしました')
    } catch (err) {
      console.error('push unsubscribe failed:', err)
      setNotifStatus('通知の解除に失敗しました')
    } finally {
      setNotifLoading(false)
    }
  }, [])

  const sendTest = useCallback(async () => {
    setNotifLoading(true)
    setNotifStatus(null)
    try {
      await apiPushTest()
      setNotifStatus('テスト通知を送信しました')
    } catch {
      setNotifStatus('テスト送信に失敗しました')
    } finally {
      setNotifLoading(false)
    }
  }, [])

  if (!user) return null

  const todayStr = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Tokyo' })

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      const updated = await apiUpdateMe({
        grade,
        exam_date: examDate || null,
        daily_goal_minutes: dailyGoal,
        reminder_schedule: schedule,
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
        </div>

        <div className="bg-white rounded-2xl p-5 shadow-sm space-y-4">
          <div>
            <label className="text-xs text-gray-400 block mb-1.5">目標級</label>
            <div className="grid grid-cols-2 gap-2">
              {([['pre2', '準2級'], ['2', '2級']] as const).map(([val, label]) => (
                <button
                  key={val}
                  type="button"
                  onClick={() => setGrade(val)}
                  className={`py-2.5 rounded-xl text-sm font-bold border-2 transition-colors ${
                    grade === val
                      ? 'bg-indigo-600 text-white border-indigo-600'
                      : 'bg-white text-gray-600 border-gray-200 hover:border-indigo-300'
                  }`}
                >
                  英検 {label}
                </button>
              ))}
            </div>
          </div>
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

        {/* Push notifications */}
        {notifSupported && (
          <div className="bg-white rounded-2xl p-5 shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <p className="font-semibold text-gray-800 text-sm">毎日リマインダー通知</p>
              <button
                onClick={notifEnabled ? disableNotifications : enableNotifications}
                disabled={notifLoading}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-50 ${
                  notifEnabled ? 'bg-indigo-600' : 'bg-gray-200'
                }`}
                aria-label={notifEnabled ? '通知をオフ' : '通知をオン'}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                    notifEnabled ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            {notifEnabled && (
              <>
                <div>
                  <p className="text-xs text-gray-400 mb-3">曜日ごとの通知時刻</p>
                  <div className="space-y-2">
                    {DAY_LABELS.map((label, i) => {
                      const key = String(i)
                      const enabled = key in schedule
                      const time = schedule[key] ?? DEFAULT_TIME
                      return (
                        <div key={i} className="flex items-center gap-3">
                          <button
                            type="button"
                            onClick={() =>
                              setSchedule((prev) => {
                                const next = { ...prev }
                                if (enabled) {
                                  delete next[key]
                                } else {
                                  next[key] = DEFAULT_TIME
                                }
                                return next
                              })
                            }
                            className={`w-9 h-9 rounded-full text-xs font-bold shrink-0 transition-colors ${
                              enabled ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-400'
                            }`}
                          >
                            {label}
                          </button>
                          {enabled ? (
                            <input
                              type="time"
                              value={time}
                              onChange={(e) =>
                                setSchedule((prev) => ({ ...prev, [key]: e.target.value }))
                              }
                              className="border-2 border-gray-200 focus:border-indigo-400 outline-none rounded-xl px-3 py-1.5 text-sm"
                            />
                          ) : (
                            <span className="text-xs text-gray-300">通知しない</span>
                          )}
                        </div>
                      )
                    })}
                  </div>
                  {Object.keys(schedule).length === 0 && (
                    <p className="text-xs text-amber-500 mt-2">曜日が選択されていません。通知は届きません。</p>
                  )}
                </div>

                <button
                  onClick={sendTest}
                  disabled={notifLoading}
                  className="text-xs text-indigo-600 underline disabled:opacity-50"
                >
                  テスト通知を送る
                </button>
              </>
            )}

            {notifStatus && (
              <p className="text-xs text-gray-500">{notifStatus}</p>
            )}
          </div>
        )}

        <button
          onClick={logout}
          className="w-full border-2 border-red-200 text-red-500 py-3.5 rounded-xl font-bold active:bg-red-50"
        >
          ログアウト
        </button>
      </div>
    </main>
  )
}
