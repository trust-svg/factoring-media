'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiGetProgress } from '@/lib/api'
import { useAuth } from '@/providers/AuthProvider'
import type { ProgressData, Skill } from '@/lib/types'

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
  onClick, gradient, glow, icon, title, sub, delay,
}: {
  onClick: () => void
  gradient: string
  glow: string
  icon: string
  title: string
  sub: string
  delay: number
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
        <p className="font-black text-white text-base leading-tight">{title}</p>
        <p className="text-white/60 text-xs font-bold mt-0.5">{sub}</p>
      </div>
      <div className="text-white/50 text-xl shrink-0 animate-sparkle">✦</div>
    </button>
  )
}

/* ── Days until exam ──────────────────────────── */
function daysUntil(dateStr: string | null): number | null {
  if (!dateStr) return null
  const ms = new Date(dateStr).getTime() - Date.now()
  return Math.max(0, Math.ceil(ms / 86_400_000))
}

/* ── Main page ────────────────────────────────── */
export default function HomePage() {
  const { user, loading, logout } = useAuth()
  const router = useRouter()
  const [progress, setProgress] = useState<ProgressData | null>(null)
  const hasRedirected = useRef(false)

  useEffect(() => {
    if (!loading && user && !user.exam_date && !hasRedirected.current) {
      hasRedirected.current = true
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
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #6D28D9, #EC4899)' }}>
        <div className="flex flex-col items-center gap-3">
          <div className="text-5xl animate-float">⭐</div>
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

      {/* Wave divider */}
      <svg viewBox="0 0 1440 40" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ display: 'block', width: '100%', marginTop: -1 }}>
        <path d="M0 0 C360 40 1080 40 1440 0 L1440 40 L0 40 Z" fill="url(#waveGrad)" />
        <defs>
          <linearGradient id="waveGrad" x1="0" y1="0" x2="1440" y2="0" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#5B21B6" />
            <stop offset="50%" stopColor="#7C3AED" />
            <stop offset="100%" stopColor="#EC4899" />
          </linearGradient>
        </defs>
      </svg>

      {/* ══════════ MAIN CONTENT ══════════ */}
      <div className="max-w-5xl mx-auto px-4 lg:px-8 pb-10" style={{ marginTop: -4 }}>

        {/* Desktop: 2-col; Mobile: stack */}
        <div className="lg:grid lg:grid-cols-[1fr_1.5fr] lg:gap-8 lg:items-start space-y-5 lg:space-y-0">

          {/* ── Left column ── */}
          <div className="space-y-4">

            {/* AI praise */}
            {progress?.praise && (
              <div
                className="card-premium rounded-3xl p-5 animate-slide-up delay-300"
                style={{ background: 'linear-gradient(135deg, #FFFBEB, #FEF3C7)', boxShadow: '0 4px 20px rgba(251,191,36,0.2), inset 0 1px 0 rgba(255,255,255,0.8)' }}
              >
                <div className="flex gap-3 items-start">
                  <span className="text-2xl animate-sparkle shrink-0">⭐</span>
                  <p className="text-amber-900 text-sm font-bold leading-relaxed">{progress.praise}</p>
                </div>
              </div>
            )}

            {/* AI advice */}
            {progress?.advice && (
              <div
                className="card-premium rounded-3xl p-5 animate-slide-up delay-400"
                style={{ background: 'linear-gradient(135deg, #F5F3FF, #EDE9FE)', boxShadow: '0 4px 20px rgba(124,58,237,0.15), inset 0 1px 0 rgba(255,255,255,0.8)' }}
              >
                <p className="text-[10px] font-black text-violet-500 uppercase tracking-widest mb-2 flex items-center gap-1.5">
                  <span>🤖</span> AIコーチ
                </p>
                <p className="text-violet-900 text-sm font-semibold leading-relaxed">{progress.advice}</p>
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
            />

            {/* Mock + vocabulary row */}
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => router.push('/mock-exam')}
                className="card-premium rounded-3xl p-5 text-left animate-slide-up delay-500"
                style={{
                  background: 'linear-gradient(135deg, #111827, #1F2937, #374151)',
                  boxShadow: '0 4px 20px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.1)',
                }}
              >
                <div className="text-3xl mb-3" style={{ animation: 'float-slow 6s ease-in-out infinite', animationDelay: '1s' }}>📝</div>
                <p className="font-black text-white text-sm">模擬試験</p>
                <p className="text-gray-500 text-[10px] font-bold mt-1">4技能 · 本番形式</p>
              </button>

              <button
                onClick={() => router.push('/vocabulary')}
                className="card-premium rounded-3xl p-5 text-left animate-slide-up delay-600"
                style={{
                  background: 'linear-gradient(135deg, #4C1D95, #6D28D9, #7C3AED)',
                  boxShadow: '0 4px 20px rgba(109,40,217,0.4), inset 0 1px 0 rgba(255,255,255,0.15)',
                }}
              >
                <div className="text-3xl mb-3" style={{ animation: 'float-slow 7s ease-in-out infinite', animationDelay: '1.6s' }}>🔗</div>
                <p className="font-black text-white text-sm">語彙ネット</p>
                <p className="text-purple-300 text-[10px] font-bold mt-1">語根クラスター</p>
              </button>
            </div>
          </div>

          {/* ── Right column: Mission cards ── */}
          <div>
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
        <div className="flex justify-center mt-8">
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
