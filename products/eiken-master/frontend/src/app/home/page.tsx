'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiGetDueFlashcards, apiGetProgress, apiGetTodayPlan, apiNotifyDailyComplete } from '@/lib/api'
import { useAuth } from '@/providers/AuthProvider'
import type { DailyPlan, DailyTask, ProgressData, Skill } from '@/lib/types'
import TutorialModal from '@/components/TutorialModal'
import InstallBanner from '@/components/InstallBanner'
import Mascot from '@/components/Mascot'

/* ── Circular progress ring ─────────────────── */
function RingProgress({ pct, size = 140 }: { pct: number; size?: number }) {
  const r = size * 0.4
  const circ = 2 * Math.PI * r
  const offset = circ - circ * Math.min(pct / 100, 1)
  const color = pct >= 70 ? '#10B981' : pct >= 50 ? '#F59E0B' : '#EF4444'
  const glow  = pct >= 70 ? 'rgba(16,185,129,0.6)' : pct >= 50 ? 'rgba(245,158,11,0.6)' : 'rgba(239,68,68,0.5)'

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)', overflow: 'visible' }}>
        {/* Track */}
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="11" />
        {/* Fill */}
        <circle
          cx={size/2} cy={size/2} r={r}
          fill="none" stroke={color} strokeWidth="11"
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          className="animate-ring-fill"
          style={{ filter: `drop-shadow(0 0 8px ${glow})` }}
        />
      </svg>
      <div className="absolute flex flex-col items-center animate-count-up">
        <span className="font-black text-white leading-none" style={{ fontSize: size * 0.22 }}>
          {pct}<span style={{ fontSize: size * 0.12 }}>%</span>
        </span>
        <span className="text-white/60 font-bold" style={{ fontSize: size * 0.085 }}>合格確率</span>
      </div>
    </div>
  )
}

/* ── Skill breakdown mini bars ───────────────── */
const SKILL_META: Record<string, { label: string; color: string }> = {
  reading:   { label: '読', color: '#818CF8' },
  listening: { label: '聞', color: '#34D399' },
  writing:   { label: '書', color: '#FBBF24' },
  speaking:  { label: '話', color: '#F472B6' },
}

function SkillBars({ breakdown }: { breakdown: ProgressData['skill_breakdown'] }) {
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-2.5">
      {(Object.entries(SKILL_META) as [keyof typeof SKILL_META, { label: string; color: string }][]).map(([key, meta]) => {
        const val = breakdown[key as keyof typeof breakdown]
        const pct = val != null ? Math.round(val * 100) : 0
        return (
          <div key={key}>
            <div className="flex justify-between items-center mb-1">
              <span className="text-white/60 text-[11px] font-bold">{meta.label}</span>
              <span className="text-white text-[11px] font-black">{val != null ? `${pct}%` : '—'}</span>
            </div>
            <div className="h-1.5 rounded-full" style={{ background: 'rgba(255,255,255,0.1)' }}>
              {val != null && (
                <div
                  className="h-1.5 rounded-full animate-bar-fill"
                  style={{ width: `${pct}%`, background: meta.color, boxShadow: `0 0 6px ${meta.color}` }}
                />
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/* ── Streak badge ─────────────────────────────── */
function StreakBadge({ streak }: { streak: number }) {
  return (
    <div className="glass-dark flex items-center gap-2 rounded-2xl px-3 py-2 animate-pop-in">
      <span className="text-2xl animate-fire inline-block leading-none">🔥</span>
      <div>
        <p className="text-white font-black text-lg leading-none">{streak}</p>
        <p className="text-white/50 text-[10px] font-bold leading-none mt-0.5">日連続</p>
      </div>
    </div>
  )
}

/* ── Title badge based on streak ───────────────── */
function getTitle(streak: number): { label: string; emoji: string; color: string } {
  if (streak >= 30) return { label: '英検マスター', emoji: '👑', color: '#F59E0B' }
  if (streak >= 14) return { label: '英語の達人',   emoji: '⭐', color: '#8B5CF6' }
  if (streak >=  7) return { label: '努力家',       emoji: '🔥', color: '#EF4444' }
  if (streak >=  3) return { label: '学習中',       emoji: '📚', color: '#3B82F6' }
  return                    { label: '見習い',       emoji: '🐣', color: '#6B7280' }
}

function TitleBadge({ streak }: { streak: number }) {
  const t = getTitle(streak)
  return (
    <span
      className="text-[10px] font-black px-2 py-0.5 rounded-full"
      style={{ background: `${t.color}22`, color: t.color, border: `1px solid ${t.color}44` }}
    >
      {t.emoji} {t.label}
    </span>
  )
}

/* ── Pace status badge ──────────────────────────── */
function PaceStatus({ trend, passProbability }: { trend: 'up' | 'flat' | 'down'; passProbability: number | null }) {
  if (passProbability === null) return null

  const config = {
    up:   { emoji: '📈', text: '上昇中！このペースで合格圏内',     bg: 'rgba(16,185,129,0.18)', color: '#6EE7B7' },
    flat: { emoji: '→',  text: '毎日続ければ合格圏内に入れるよ',   bg: 'rgba(255,255,255,0.10)', color: 'rgba(255,255,255,0.7)' },
    down: { emoji: '⚠️', text: 'もう少しペースアップが必要かも',   bg: 'rgba(239,68,68,0.18)',   color: '#FCA5A5' },
  }[trend]

  return (
    <div
      className="rounded-2xl px-4 py-2.5 flex items-center gap-2"
      style={{ background: config.bg, border: '1px solid rgba(255,255,255,0.10)' }}
    >
      <span className="text-base leading-none shrink-0">{config.emoji}</span>
      <p className="text-[12px] font-bold" style={{ color: config.color }}>{config.text}</p>
    </div>
  )
}

/* ── Mission card (3D tilt + shimmer) ─────────── */
interface Mission {
  skill: Skill
  label: string
  emoji: string
  gradient: string
  glowColor: string
  accuracy: number | null
}

function MissionCard({ m, delay }: { m: Mission; delay: number }) {
  const router = useRouter()
  const ref = useRef<HTMLButtonElement>(null)
  const [tilt, setTilt] = useState({ x: 0, y: 0 })
  const [hovered, setHovered] = useState(false)

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (!ref.current) return
    const r = ref.current.getBoundingClientRect()
    const x = (e.clientX - r.left) / r.width - 0.5
    const y = (e.clientY - r.top)  / r.height - 0.5
    setTilt({ x: y * -10, y: x * 10 })
  }, [])

  const onMouseLeave = useCallback(() => {
    setHovered(false)
    setTilt({ x: 0, y: 0 })
  }, [])

  const pct = m.accuracy != null ? Math.round(m.accuracy * 100) : null

  return (
    <button
      ref={ref}
      onClick={() => router.push(`/study/${m.skill}`)}
      onMouseMove={onMouseMove}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={onMouseLeave}
      className="card-premium rounded-3xl text-left animate-slide-up"
      style={{
        animationDelay: `${delay}ms`,
        background: m.gradient,
        transform: hovered
          ? `perspective(700px) rotateX(${tilt.x}deg) rotateY(${tilt.y}deg) translateY(-6px) scale(1.03)`
          : 'perspective(700px) rotateX(0) rotateY(0) translateY(0) scale(1)',
        transition: hovered ? 'transform 0.12s ease-out, box-shadow 0.2s ease' : 'transform 0.4s ease-out, box-shadow 0.3s ease',
        boxShadow: hovered
          ? `0 2px 4px rgba(0,0,0,0.2), 0 12px 32px ${m.glowColor}, 0 32px 64px ${m.glowColor.replace('0.5','0.2')}, inset 0 1px 0 rgba(255,255,255,0.3)`
          : `0 2px 8px rgba(0,0,0,0.15), 0 8px 24px ${m.glowColor.replace('0.5','0.2')}, inset 0 1px 0 rgba(255,255,255,0.2)`,
      }}
    >
      {/* BG emoji decoration */}
      <div
        className="absolute right-3 top-3 pointer-events-none select-none"
        style={{ fontSize: 64, opacity: 0.15, animation: `float-slow ${5 + delay * 0.001}s ease-in-out infinite`, animationDelay: `${delay * 0.3}ms` }}
      >
        {m.emoji}
      </div>

      <div className="relative z-10 p-5">
        {/* Emoji */}
        <div className="text-4xl mb-4 leading-none" style={{ animation: `float ${4 + delay * 0.001}s ease-in-out infinite`, animationDelay: `${delay * 0.4}ms` }}>
          {m.emoji}
        </div>

        {/* Label */}
        <p className="font-black text-white text-base leading-tight mb-1">{m.label}</p>

        {/* Accuracy */}
        {pct !== null ? (
          <div className="mt-3">
            <div className="flex justify-between items-center mb-1.5">
              <span className="text-[10px] text-white/60 font-bold uppercase tracking-wide">正答率</span>
              <span className="text-xs text-white font-black">{pct}%</span>
            </div>
            <div className="h-1.5 rounded-full" style={{ background: 'rgba(255,255,255,0.15)' }}>
              <div
                className="h-1.5 rounded-full animate-bar-fill"
                style={{
                  width: `${pct}%`,
                  background: 'rgba(255,255,255,0.9)',
                  boxShadow: '0 0 8px rgba(255,255,255,0.6)',
                  animationDelay: `${delay + 200}ms`,
                }}
              />
            </div>
          </div>
        ) : (
          <p className="text-white/40 text-[11px] font-bold mt-3">まだデータなし</p>
        )}

        {/* CTA */}
        <div className="mt-4 flex items-center justify-between">
          <span className="text-white/80 text-xs font-black uppercase tracking-wider">スタート</span>
          <div
            className="w-7 h-7 rounded-xl flex items-center justify-center text-white text-xs font-black"
            style={{ background: 'rgba(255,255,255,0.2)' }}
          >
            →
          </div>
        </div>
      </div>
    </button>
  )
}

/* ── Big CTA card ─────────────────────────────── */
function BigCta({
  onClick, gradient, glow, icon, title, sub, delay, badge,
}: {
  onClick: () => void
  gradient: string
  glow: string
  icon: string
  title: string
  sub: string
  delay: number
  badge?: number
}) {
  const [hovered, setHovered] = useState(false)
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className="card-premium w-full rounded-3xl p-5 flex items-center gap-4 text-left animate-slide-up"
      style={{
        animationDelay: `${delay}ms`,
        background: gradient,
        transform: hovered ? 'translateY(-4px) scale(1.02)' : 'translateY(0) scale(1)',
        transition: 'transform 0.2s cubic-bezier(0.34,1.2,0.64,1)',
        boxShadow: hovered
          ? `0 4px 8px rgba(0,0,0,0.2), 0 16px 40px ${glow}, inset 0 1px 0 rgba(255,255,255,0.25)`
          : `0 2px 8px rgba(0,0,0,0.15), 0 8px 24px ${glow.replace('0.45','0.2')}, inset 0 1px 0 rgba(255,255,255,0.2)`,
      }}
    >
      <div
        className="w-14 h-14 rounded-2xl flex items-center justify-center text-3xl shrink-0"
        style={{ background: 'rgba(255,255,255,0.15)', animation: 'float-slow 5s ease-in-out infinite' }}
      >
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="font-black text-white text-base leading-tight">{title}</p>
          {badge != null && badge > 0 && (
            <span className="bg-red-500 text-white text-[10px] font-black px-1.5 py-0.5 rounded-full leading-none">{badge}</span>
          )}
        </div>
        <p className="text-white/60 text-xs font-bold mt-0.5">{sub}</p>
      </div>
      <div className="text-white/50 text-xl shrink-0 animate-sparkle">✦</div>
    </button>
  )
}

/* ── Daily plan card ─────────────────────────── */
const SKILL_TASK_META: Record<string, { emoji: string; color: string }> = {
  reading:   { emoji: '📖', color: 'text-blue-600' },
  listening: { emoji: '🎧', color: 'text-teal-600' },
  writing:   { emoji: '✍️', color: 'text-orange-600' },
  speaking:  { emoji: '🎤', color: 'text-pink-600' },
  flashcards: { emoji: '🃏', color: 'text-indigo-600' },
}

const SKILL_ROUTE: Record<string, string> = {
  reading: '/study/reading',
  listening: '/study/listening',
  writing: '/study/writing',
  speaking: '/study/speaking',
  flashcards: '/flashcards',
}

function DailyPlanCard({ plan, onRefresh, refreshing, onTaskClick, completedTasks, advice, praise, weeklySessions }: {
  plan: DailyPlan
  onRefresh: () => void
  refreshing: boolean
  onTaskClick: (skill: string) => void
  completedTasks: Set<number>
  advice?: string | null
  praise?: string | null
  weeklySessions?: number
}) {
  const total = plan.tasks.reduce((s, t) => s + t.minutes, 0)
  const allDone = plan.tasks.length > 0 && completedTasks.size >= plan.tasks.length

  return (
    <div
      className="card-premium rounded-3xl p-5 animate-slide-up"
      style={{
        background: 'linear-gradient(135deg, #EFF6FF, #DBEAFE, #EDE9FE)',
        boxShadow: '0 4px 20px rgba(99,102,241,0.12), inset 0 1px 0 rgba(255,255,255,0.9)',
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">🤖</span>
          <p className="text-[11px] font-black text-indigo-600 uppercase tracking-widest">今日のAIプラン</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-indigo-400 font-bold">
            {completedTasks.size}/{plan.tasks.length}完了 · {total}分
          </span>
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="text-indigo-400 hover:text-indigo-600 disabled:opacity-40 text-base transition-colors leading-none"
            aria-label="プランを再生成"
            title="プランを再生成"
          >
            {refreshing ? '…' : '↻'}
          </button>
        </div>
      </div>
      <p className="text-indigo-800 text-sm font-semibold leading-relaxed mb-4">{plan.message}</p>

      {/* All-done celebration */}
      {allDone && (
        <div
          className="rounded-2xl p-4 mb-4 space-y-3"
          style={{
            background: 'linear-gradient(135deg, #D1FAE5, #A7F3D0)',
            boxShadow: '0 2px 12px rgba(16,185,129,0.2)',
          }}
        >
          <div className="flex items-center gap-3">
            <Mascot scene="celebrate" size={64} className="shrink-0" />
            <div>
              <p className="text-emerald-800 font-black text-base leading-tight">今日の学習完了！🎉</p>
              <p className="text-emerald-700 text-xs font-semibold mt-1">
                {plan.tasks.length}タスク全部やり切ったね！すごい！
              </p>
              {weeklySessions != null && weeklySessions > 0 && (
                <p className="text-emerald-600 text-[11px] font-bold mt-1">
                  📊 今週 {weeklySessions} セッション達成
                </p>
              )}
            </div>
          </div>
          {praise && (
            <div className="bg-white/70 rounded-xl px-3 py-2.5">
              <p className="text-[10px] text-emerald-500 font-black uppercase tracking-widest mb-1">🦉 フクロウ博士より</p>
              <p className="text-emerald-900 text-xs font-semibold leading-relaxed">{praise}</p>
            </div>
          )}
          {advice && !praise && (
            <div className="bg-white/60 rounded-xl px-3 py-2.5">
              <p className="text-[10px] text-emerald-500 font-black uppercase tracking-widest mb-1">AIコーチより</p>
              <p className="text-emerald-900 text-xs font-semibold leading-relaxed">{advice}</p>
            </div>
          )}
          <WeekStampCard todayStamped={true} />
        </div>
      )}

      <div className="space-y-2">
        {plan.tasks.map((task: DailyTask, i: number) => {
          const meta = SKILL_TASK_META[task.skill] ?? { emoji: '📌', color: 'text-gray-600' }
          const hasRoute = task.skill in SKILL_ROUTE
          const done = completedTasks.has(i)
          return (
            <button
              key={i}
              onClick={() => onTaskClick(task.skill)}
              disabled={!hasRoute}
              className={`w-full flex items-center gap-3 rounded-2xl px-3 py-2.5 text-left transition-all active:scale-[0.98] disabled:cursor-default ${
                done ? 'bg-emerald-50/80 border border-emerald-200/60' : 'bg-white/70 hover:bg-white'
              }`}
            >
              {/* Status indicator */}
              <div className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-sm ${
                done ? 'bg-emerald-500 text-white' : 'bg-gray-100 text-gray-300'
              }`}>
                {done ? '✓' : <span className="text-base">{meta.emoji}</span>}
              </div>
              <p className={`text-sm font-bold flex-1 min-w-0 ${done ? 'line-through text-gray-400' : meta.color}`}>
                {task.description}
              </p>
              <div className="flex items-center gap-1.5 shrink-0">
                <span className={`text-xs font-bold ${done ? 'text-gray-300' : 'text-gray-400'}`}>{task.minutes}分</span>
                {hasRoute && !done && <span className="text-indigo-300 text-xs font-bold">→</span>}
                {done && <span className="text-emerald-400 text-xs font-bold">完了</span>}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

/* ── Days until exam ──────────────────────────── */
function daysUntil(dateStr: string | null): number | null {
  if (!dateStr) return null
  const ms = new Date(dateStr).getTime() - Date.now()
  return Math.max(0, Math.ceil(ms / 86_400_000))
}

/* ── localStorage helpers ────── */
function todayKey(): string {
  return new Date().toISOString().slice(0, 10)
}

// Completed tasks (which plan tasks are done today)
function loadCompletedTasks(): Set<number> {
  try {
    const raw = localStorage.getItem(`eiken-plan-done-${todayKey()}`)
    if (!raw) return new Set()
    return new Set<number>(JSON.parse(raw))
  } catch {
    return new Set()
  }
}
function saveCompletedTasks(s: Set<number>) {
  try {
    localStorage.setItem(`eiken-plan-done-${todayKey()}`, JSON.stringify([...s]))
  } catch {}
}

// Daily plan cache (fixed for the day)
function loadCachedPlan(): DailyPlan | null {
  try {
    const raw = localStorage.getItem(`eiken-daily-plan-${todayKey()}`)
    return raw ? (JSON.parse(raw) as DailyPlan) : null
  } catch {
    return null
  }
}
function cachePlan(plan: DailyPlan) {
  try {
    localStorage.setItem(`eiken-daily-plan-${todayKey()}`, JSON.stringify(plan))
  } catch {}
}
function clearCachedPlan() {
  try {
    localStorage.removeItem(`eiken-daily-plan-${todayKey()}`)
  } catch {}
}

// Notify once per day (persisted across page navigations)
const NOTIFY_KEY = 'eiken-notify-sent'
function wasNotifiedToday(): boolean {
  try { return localStorage.getItem(NOTIFY_KEY) === todayKey() } catch { return false }
}
function markNotifiedToday() {
  try { localStorage.setItem(NOTIFY_KEY, todayKey()) } catch {}
}

// Stamps (one per day when all tasks done)
const STAMP_KEY = 'eiken-stamps'
function loadStamps(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(STAMP_KEY) || '{}')
  } catch {
    return {}
  }
}
function saveStampToday() {
  try {
    const stamps = loadStamps()
    stamps[todayKey()] = true
    localStorage.setItem(STAMP_KEY, JSON.stringify(stamps))
  } catch {}
}

/* ── Week stamp card ────── */
function WeekStampCard({ todayStamped }: { todayStamped: boolean }) {
  const today = new Date()
  const stamps = loadStamps()
  const key0 = todayKey()
  const dow = today.getDay()
  const mondayOffset = dow === 0 ? -6 : 1 - dow
  const monday = new Date(today)
  monday.setDate(today.getDate() + mondayOffset)
  const DAY_LABELS = ['月', '火', '水', '木', '金', '土', '日']
  const days = DAY_LABELS.map((label, i) => {
    const d = new Date(monday)
    d.setDate(monday.getDate() + i)
    const k = d.toISOString().slice(0, 10)
    return { label, isToday: k === key0, stamped: k === key0 ? todayStamped : !!stamps[k] }
  })
  return (
    <div className="bg-white/50 rounded-2xl px-4 py-3">
      <p className="text-[10px] text-emerald-600 font-black uppercase tracking-widest mb-2">今週のスタンプ</p>
      <div className="flex justify-between gap-1">
        {days.map((d) => (
          <div key={d.label} className="flex flex-col items-center gap-1">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-base transition-all ${
                d.stamped
                  ? 'bg-yellow-400 shadow-md'
                  : d.isToday
                  ? 'bg-emerald-50 border-2 border-emerald-300'
                  : 'bg-white/40 border border-gray-200'
              }`}
            >
              {d.stamped ? '⭐' : ''}
            </div>
            <p className={`text-[9px] font-black ${d.isToday ? 'text-emerald-700' : d.stamped ? 'text-yellow-600' : 'text-gray-400'}`}>
              {d.label}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── Main page ────────────────────────────────── */
export default function HomePage() {
  const { user, loading, logout } = useAuth()
  const router = useRouter()
  const [progress, setProgress] = useState<ProgressData | null>(null)
  const [dailyPlan, setDailyPlan] = useState<DailyPlan | null>(null)
  const [planRefreshing, setPlanRefreshing] = useState(false)
  const [dueCount, setDueCount] = useState<number | null>(null)
  const [completedTasks, setCompletedTasks] = useState<Set<number>>(new Set())
  const hasRedirected = useRef(false)
  const pendingSkillRef = useRef<string | null>(null)

  // On mount: capture sessionStorage skill-done signal + restore completed tasks
  useEffect(() => {
    const skill = sessionStorage.getItem('eiken-skill-done')
    if (skill) {
      sessionStorage.removeItem('eiken-skill-done')
      pendingSkillRef.current = skill
    }
    setCompletedTasks(loadCompletedTasks())
  }, [])

  const handleTaskClick = useCallback((skill: string) => {
    const route = SKILL_ROUTE[skill]
    if (route) router.push(route)
  }, [router])

  useEffect(() => {
    if (!loading && user && !user.exam_date && !hasRedirected.current) {
      hasRedirected.current = true
      router.replace('/onboarding')
    }
  }, [loading, user, router])

  useEffect(() => {
    if (!loading && user) {
      apiGetProgress().then(setProgress).catch(() => {})
      apiGetDueFlashcards().then((cards) => setDueCount(cards.length)).catch(() => {})

      const autoCheckSkill = (plan: DailyPlan) => {
        const skill = pendingSkillRef.current
        if (!skill) return
        pendingSkillRef.current = null
        const completed = loadCompletedTasks()
        const idx = plan.tasks.findIndex((t, i) => t.skill === skill && !completed.has(i))
        if (idx !== -1) {
          const next = new Set(completed)
          next.add(idx)
          saveCompletedTasks(next)
          setCompletedTasks(next)
        }
      }

      const cached = loadCachedPlan()
      if (cached) {
        setDailyPlan(cached)
        autoCheckSkill(cached)
      } else {
        apiGetTodayPlan()
          .then((plan) => {
            setDailyPlan(plan)
            cachePlan(plan)
            autoCheckSkill(plan)
          })
          .catch(() => {})
      }
    }
  }, [loading, user])

  // Save stamp and send Telegram completion notification when all tasks done
  const allDone = dailyPlan
    ? dailyPlan.tasks.length > 0 && completedTasks.size >= dailyPlan.tasks.length
    : false
  useEffect(() => {
    if (!allDone) return
    saveStampToday()
    if (!wasNotifiedToday()) {
      markNotifiedToday()
      apiNotifyDailyComplete().catch(() => {})
    }
  }, [allDone])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #6D28D9, #EC4899)' }}>
        <div className="flex flex-col items-center gap-3">
          <Mascot scene="thinking" size={96} />
          <p className="text-white/70 text-sm font-bold tracking-wide">よみこみちゅう…</p>
        </div>
      </div>
    )
  }

  if (!user) return null

  const days = daysUntil(user.exam_date)
  const gradeLabel = user.grade === 'pre2' ? '準2級' : '2級'
  const pct = progress?.pass_probability != null ? Math.round(progress.pass_probability * 100) : null
  const breakdown = progress?.skill_breakdown

  const missions: Mission[] = [
    { skill: 'reading',   label: 'リーディング', emoji: '📖', gradient: 'linear-gradient(135deg,#4F7CF9 0%,#7B3CF9 100%)', glowColor: 'rgba(79,124,249,0.5)',  accuracy: breakdown?.reading   ?? null },
    { skill: 'listening', label: 'リスニング',   emoji: '🎧', gradient: 'linear-gradient(135deg,#0ECFA0 0%,#0EAEE0 100%)', glowColor: 'rgba(14,207,160,0.5)', accuracy: breakdown?.listening ?? null },
    { skill: 'writing',   label: 'ライティング', emoji: '✍️', gradient: 'linear-gradient(135deg,#FFB020 0%,#FF5C30 100%)', glowColor: 'rgba(255,176,32,0.5)',  accuracy: breakdown?.writing   ?? null },
    { skill: 'speaking',  label: 'スピーキング', emoji: '🎤', gradient: 'linear-gradient(135deg,#FF6BA0 0%,#C83870 100%)', glowColor: 'rgba(255,107,160,0.5)', accuracy: breakdown?.speaking  ?? null },
  ]

  return (
    <main className="min-h-screen bg-animated">
      <TutorialModal />
      <InstallBanner />

      {/* ══════════ HERO HEADER ══════════ */}
      <div
        className="relative overflow-hidden"
        style={{ background: 'linear-gradient(135deg, #5B21B6 0%, #7C3AED 35%, #A855F7 65%, #EC4899 100%)' }}
      >
        {/* Decorative light blobs */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute rounded-full blur-3xl opacity-30" style={{ width: 320, height: 320, background: '#F97316', top: '-20%', right: '-10%' }} />
          <div className="absolute rounded-full blur-3xl opacity-20" style={{ width: 200, height: 200, background: '#06B6D4', bottom: '-10%', left: '5%' }} />
          <div className="absolute rounded-full blur-2xl opacity-25" style={{ width: 160, height: 160, background: '#FBBF24', top: '10%', left: '40%' }} />
        </div>

        {/* Content — desktop: 2-col grid; mobile: stack */}
        <div className="relative max-w-5xl mx-auto px-4 lg:px-8 pt-10 pb-8 lg:pb-10">

          {/* Top bar */}
          <div className="flex items-start justify-between mb-6 lg:mb-8 animate-slide-up">
            <div>
              <p className="text-white/50 text-[11px] font-black uppercase tracking-widest">英検マスター</p>
              <h1 className="text-white font-black text-2xl lg:text-3xl mt-0.5">
                {user.username}<span className="text-white/50 text-lg lg:text-xl font-bold">さん</span>
              </h1>
              <div className="flex items-center flex-wrap gap-2 mt-2">
                <span className="glass-dark text-white text-xs font-black px-3 py-1 rounded-full">
                  英検 {gradeLabel}
                </span>
                {progress && <TitleBadge streak={progress.streak} />}
                {progress?.trend === 'up' && (
                  <span className="glass-dark text-white text-xs font-bold px-3 py-1 rounded-full">
                    📈 上昇中
                  </span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0 ml-4">
              {progress && <StreakBadge streak={progress.streak} />}
              <button
                onClick={() => router.push('/settings')}
                className="glass-dark w-10 h-10 rounded-2xl flex items-center justify-center text-white hover:bg-white/20 transition-colors animate-pop-in"
                aria-label="設定"
              >
                ⚙️
              </button>
            </div>
          </div>

          {/* Stats row — desktop 3-col, mobile 2-col */}
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 lg:gap-6">
            {/* Pass probability ring */}
            <div className="flex items-center justify-center lg:justify-start animate-pop-in delay-200">
              {pct !== null ? (
                <RingProgress pct={pct} size={130} />
              ) : (
                <div className="w-32 h-32 rounded-full border-4 border-white/15 flex items-center justify-center">
                  <div className="text-center">
                    <p className="text-white/30 text-3xl font-black">—</p>
                    <p className="text-white/30 text-[10px] font-bold mt-1">未記録</p>
                  </div>
                </div>
              )}
            </div>

            {/* Days countdown */}
            {days !== null && (
              <div className="flex items-center animate-slide-up delay-300">
                <div className="glass-dark rounded-3xl px-6 py-5 text-center w-full">
                  <p className="text-white/50 text-[10px] font-black uppercase tracking-widest mb-1">試験まで</p>
                  <p className="text-white font-black leading-none" style={{ fontSize: 52 }}>{days}</p>
                  <p className="text-white/50 text-sm font-bold mt-1">日</p>
                </div>
              </div>
            )}

            {/* Skill breakdown — desktop only or when has data */}
            {breakdown && (
              <div className="col-span-2 lg:col-span-1 animate-slide-up delay-400">
                <div className="glass-dark rounded-3xl px-4 py-4">
                  <p className="text-white/50 text-[10px] font-black uppercase tracking-widest mb-3">4技能スコア</p>
                  <SkillBars breakdown={breakdown} />
                </div>
              </div>
            )}
          </div>

          {/* Pace status */}
          {progress && (
            <div className="mt-3 animate-slide-up delay-450">
              <PaceStatus
                trend={progress.trend}
                passProbability={progress.pass_probability}
              />
            </div>
          )}

          {/* Detail link */}
          <div className="mt-4 animate-slide-up delay-500">
            <button
              onClick={() => router.push('/progress')}
              className="text-white/60 text-xs font-bold hover:text-white transition-colors flex items-center gap-1.5"
            >
              <span>詳細レポートを見る</span>
              <span className="text-white/40">→</span>
            </button>
          </div>
        </div>

      </div>

      {/* ══════════ MAIN CONTENT ══════════ */}
      <div className="max-w-5xl mx-auto px-4 lg:px-8 pt-6 pb-14">

        {/* ── 今日の目標 + AIプラン — 常に最上段 (mobile / desktop 共通) ── */}
        <div className="space-y-4 mb-5">

          {/* Daily goal */}
          <div
            className="card-premium rounded-3xl p-5 animate-slide-up"
            style={{
              background: 'linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 50%, #D1FAE5 100%)',
              boxShadow: '0 4px 20px rgba(16,185,129,0.15), inset 0 1px 0 rgba(255,255,255,0.9)',
            }}
          >
            <div className="flex items-start gap-3">
              <span className="text-2xl shrink-0">🎯</span>
              <div className="flex-1 min-w-0">
                <p className="text-[10px] font-black text-emerald-600 uppercase tracking-widest mb-1">今日の目標</p>
                <p className="text-emerald-900 text-sm font-black">{user.daily_goal_minutes}分学習</p>
                <p className="text-emerald-700 text-xs font-semibold mt-1.5 leading-relaxed">
                  {days !== null && days > 0
                    ? `試験まであと${days}日。今日も1問ずつ積み上げよう！`
                    : '毎日コツコツが合格への近道！'}
                </p>
              </div>
            </div>
          </div>

          {/* Daily AI plan */}
          {dailyPlan && (
            <DailyPlanCard
              plan={dailyPlan}
              refreshing={planRefreshing}
              onTaskClick={handleTaskClick}
              completedTasks={completedTasks}
              advice={progress?.advice}
              praise={progress?.praise}
              weeklySessions={progress?.weekly_sessions}
              onRefresh={async () => {
                setPlanRefreshing(true)
                clearCachedPlan()
                try {
                  const fresh = await apiGetTodayPlan()
                  setDailyPlan(fresh)
                  cachePlan(fresh)
                } catch {
                  // silently ignore
                } finally {
                  setPlanRefreshing(false)
                }
              }}
            />
          )}
        </div>

        {/* ── 2カラムグリッド: mobile = ミッション→その他, desktop = 左右並列 ── */}
        <div className="flex flex-col lg:grid lg:grid-cols-[1fr_1.5fr] lg:gap-8 lg:items-start gap-5">

          {/* ── Left column (utilities) — mobile で order-2 ── */}
          <div className="space-y-4 order-2 lg:order-1">

            {/* AI praise */}
            {progress?.praise && (
              <div
                className="card-premium rounded-3xl p-4 animate-slide-up delay-300"
                style={{ background: 'linear-gradient(135deg, #FFFBEB, #FEF3C7)', boxShadow: '0 4px 20px rgba(251,191,36,0.2), inset 0 1px 0 rgba(255,255,255,0.8)' }}
              >
                <div className="flex gap-3 items-center">
                  <Mascot scene="correct" size={56} className="shrink-0" />
                  <p className="text-amber-900 text-sm font-bold leading-relaxed">{progress.praise}</p>
                </div>
              </div>
            )}

            {/* AI advice */}
            {progress?.advice && (
              <div
                className="card-premium rounded-3xl p-4 animate-slide-up delay-400"
                style={{ background: 'linear-gradient(135deg, #F5F3FF, #EDE9FE)', boxShadow: '0 4px 20px rgba(124,58,237,0.15), inset 0 1px 0 rgba(255,255,255,0.8)' }}
              >
                <div className="flex gap-3 items-start">
                  <Mascot scene="explain" size={56} className="shrink-0 mt-0.5" />
                  <div className="min-w-0">
                    <p className="text-[10px] font-black text-violet-400 uppercase tracking-widest mb-1">AIコーチ</p>
                    <p className="text-violet-900 text-sm font-semibold leading-relaxed">{progress.advice}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Flashcard CTA */}
            <BigCta
              onClick={() => router.push('/flashcards')}
              gradient="linear-gradient(135deg, #1E1B4B 0%, #2D2A6E 50%, #4338CA 100%)"
              glow="rgba(67,56,202,0.45)"
              icon="🃏"
              title="今日の単語カード"
              sub="SM-2 間隔反復 · 科学的暗記法"
              delay={350}
              badge={dueCount ?? undefined}
            />

            {/* Mock + vocabulary row */}
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => router.push('/mock-exam')}
                className="card-premium rounded-3xl p-5 text-left animate-slide-up delay-500 min-h-[130px] flex flex-col"
                style={{
                  background: 'linear-gradient(135deg, #111827, #1F2937, #374151)',
                  boxShadow: '0 4px 20px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.1)',
                }}
              >
                <div className="text-3xl" style={{ animation: 'float-slow 6s ease-in-out infinite', animationDelay: '1s' }}>📝</div>
                <div className="mt-auto">
                  <p className="font-black text-white text-sm">模擬試験</p>
                  <p className="text-gray-500 text-[10px] font-bold mt-0.5">4技能 · 本番形式</p>
                </div>
              </button>

              <button
                onClick={() => router.push('/vocabulary')}
                className="card-premium rounded-3xl p-5 text-left animate-slide-up delay-600 min-h-[130px] flex flex-col"
                style={{
                  background: 'linear-gradient(135deg, #4C1D95, #6D28D9, #7C3AED)',
                  boxShadow: '0 4px 20px rgba(109,40,217,0.4), inset 0 1px 0 rgba(255,255,255,0.15)',
                }}
              >
                <div className="text-3xl" style={{ animation: 'float-slow 7s ease-in-out infinite', animationDelay: '1.6s' }}>🔗</div>
                <div className="mt-auto">
                  <p className="font-black text-white text-sm">語彙ネット</p>
                  <p className="text-purple-300 text-[10px] font-bold mt-0.5">語根クラスター</p>
                </div>
              </button>
            </div>
          </div>

          {/* ── Right column: Mission cards — mobile で order-1 (最初) ── */}
          <div className="order-1 lg:order-2">
            <div className="flex items-center gap-2 mb-4 lg:mb-5 animate-slide-up delay-200">
              <div className="w-1 h-5 rounded-full" style={{ background: 'linear-gradient(#7C3AED, #EC4899)' }} />
              <h2 className="font-black text-gray-800 text-sm tracking-widest uppercase">4技能ミッション</h2>
            </div>
            <div className="grid grid-cols-2 gap-3 lg:gap-4">
              {missions.map((m, i) => (
                <MissionCard key={m.skill} m={m} delay={200 + i * 80} />
              ))}
            </div>
          </div>
        </div>

        {/* Logout */}
        <div className="flex justify-center mt-10 pt-6 border-t border-gray-200/50">
          <button
            onClick={logout}
            className="text-gray-400 text-xs font-bold hover:text-gray-600 transition-colors px-6 py-2.5 rounded-2xl hover:bg-white/60"
          >
            ログアウト
          </button>
        </div>
      </div>
    </main>
  )
}
