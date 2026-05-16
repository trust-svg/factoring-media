'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiGetProgress } from '@/lib/api'
import { useAuth } from '@/providers/AuthProvider'
import type { ProgressData, Skill } from '@/lib/types'

/* ── Circular progress ring ───────────────────── */
function RingProgress({ pct }: { pct: number }) {
  const r = 52
  const circ = 2 * Math.PI * r
  const fill = circ - circ * Math.min(pct / 100, 1)

  const color =
    pct >= 70 ? '#10B981' : pct >= 50 ? '#F59E0B' : '#EF4444'
  const glow =
    pct >= 70
      ? '0 0 20px rgba(16,185,129,0.5)'
      : pct >= 50
      ? '0 0 20px rgba(245,158,11,0.5)'
      : '0 0 20px rgba(239,68,68,0.4)'

  return (
    <div className="relative flex items-center justify-center" style={{ width: 128, height: 128 }}>
      <svg width="128" height="128" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx="64" cy="64" r={r} fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="10" />
        <circle
          cx="64" cy="64" r={r}
          fill="none" stroke={color} strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={fill}
          className="animate-ring-fill"
          style={{ filter: `drop-shadow(${glow})`, transition: 'stroke-dashoffset 1.2s ease-out' }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-3xl font-black text-white animate-count-up" style={{ lineHeight: 1 }}>
          {pct}<span className="text-lg font-bold">%</span>
        </span>
        <span className="text-[10px] font-bold text-white/70 mt-0.5">合格確率</span>
      </div>
    </div>
  )
}

/* ── Streak badge ─────────────────────────────── */
function StreakBadge({ streak }: { streak: number }) {
  return (
    <div className="flex items-center gap-1.5 bg-white/20 rounded-2xl px-3 py-1.5 backdrop-blur-sm animate-pop-in">
      <span className="text-xl animate-fire inline-block">🔥</span>
      <div>
        <p className="text-white font-black text-base leading-none">{streak}</p>
        <p className="text-white/70 text-[9px] font-bold leading-none mt-0.5">連続</p>
      </div>
    </div>
  )
}

/* ── Skill mission card ───────────────────────── */
interface MissionCard {
  skill: Skill
  label: string
  emoji: string
  gradient: string
  shadow: string
  accuracy: number | null
}

function MissionCard({ card, delay }: { card: MissionCard; delay: number }) {
  const router = useRouter()
  const [hovered, setHovered] = useState(false)

  return (
    <button
      onClick={() => router.push(`/study/${card.skill}`)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className="relative rounded-3xl overflow-hidden text-left animate-slide-up"
      style={{
        animationDelay: `${delay}ms`,
        background: card.gradient,
        boxShadow: hovered ? card.shadow : '0 4px 20px rgba(0,0,0,0.15)',
        transform: hovered ? 'translateY(-4px) scale(1.02)' : 'translateY(0) scale(1)',
        transition: 'transform 0.25s cubic-bezier(0.34,1.56,0.64,1), box-shadow 0.25s ease',
      }}
    >
      {/* Background decoration */}
      <div
        className="absolute -right-4 -top-4 text-6xl opacity-20 pointer-events-none"
        style={{
          animation: `float ${3 + delay * 0.002}s ease-in-out infinite`,
          animationDelay: `${delay * 0.5}ms`,
        }}
      >
        {card.emoji}
      </div>

      <div className="relative p-4">
        <div className="text-4xl mb-3">{card.emoji}</div>
        <p className="font-black text-white text-sm leading-tight">{card.label}</p>

        {card.accuracy !== null && (
          <div className="mt-2.5">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] text-white/70 font-bold">正答率</span>
              <span className="text-[10px] text-white font-black">{Math.round(card.accuracy * 100)}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-white/20">
              <div
                className="h-1.5 rounded-full bg-white/90 transition-all duration-700"
                style={{ width: `${Math.round(card.accuracy * 100)}%` }}
              />
            </div>
          </div>
        )}

        <div className="mt-3 flex items-center gap-1">
          <span className="text-white/90 text-xs font-bold">スタート</span>
          <span className="text-white text-xs">→</span>
        </div>
      </div>
    </button>
  )
}

/* ── Days countdown ───────────────────────────── */
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
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #7C3AED 0%, #EC4899 50%, #F97316 100%)' }}>
        <div className="flex flex-col items-center gap-3">
          <div className="text-5xl animate-float">⭐</div>
          <p className="text-white/80 text-sm font-bold">よみこみちゅう...</p>
        </div>
      </div>
    )
  }

  if (!user) return null

  const days = daysUntil(user.exam_date)
  const gradeLabel = user.grade === 'pre2' ? '準2級' : '2級'
  const pct = progress?.pass_probability != null ? Math.round(progress.pass_probability * 100) : null
  const breakdown = progress?.skill_breakdown

  const missions: MissionCard[] = [
    {
      skill: 'reading',
      label: 'リーディング',
      emoji: '📖',
      gradient: 'linear-gradient(135deg, #4F9CF9 0%, #7B4CF9 100%)',
      shadow: '0 12px 40px rgba(79,156,249,0.5)',
      accuracy: breakdown?.reading ?? null,
    },
    {
      skill: 'listening',
      label: 'リスニング',
      emoji: '🎧',
      gradient: 'linear-gradient(135deg, #10D9A0 0%, #4F9CF9 100%)',
      shadow: '0 12px 40px rgba(16,217,160,0.5)',
      accuracy: breakdown?.listening ?? null,
    },
    {
      skill: 'writing',
      label: 'ライティング',
      emoji: '✍️',
      gradient: 'linear-gradient(135deg, #FFB830 0%, #FF7849 100%)',
      shadow: '0 12px 40px rgba(255,184,48,0.5)',
      accuracy: breakdown?.writing ?? null,
    },
    {
      skill: 'speaking',
      label: 'スピーキング',
      emoji: '🎤',
      gradient: 'linear-gradient(135deg, #FF6B9D 0%, #C84B84 100%)',
      shadow: '0 12px 40px rgba(255,107,157,0.5)',
      accuracy: breakdown?.speaking ?? null,
    },
  ]

  return (
    <main className="min-h-screen" style={{ background: '#F5F3FF' }}>

      {/* ── Hero header ── */}
      <div
        className="relative overflow-hidden px-4 pt-12 pb-8"
        style={{ background: 'linear-gradient(135deg, #6D28D9 0%, #7C3AED 40%, #EC4899 100%)' }}
      >
        {/* Decorative blobs */}
        <div className="absolute top-0 right-0 w-40 h-40 rounded-full opacity-20 blur-3xl" style={{ background: '#F97316', transform: 'translate(30%, -30%)' }} />
        <div className="absolute bottom-0 left-0 w-32 h-32 rounded-full opacity-15 blur-2xl" style={{ background: '#06B6D4', transform: 'translate(-20%, 30%)' }} />

        <div className="max-w-lg mx-auto">
          {/* Top bar */}
          <div className="flex items-start justify-between mb-6">
            <div className="animate-slide-up">
              <p className="text-white/70 text-xs font-bold tracking-wide uppercase">英検マスター</p>
              <h1 className="text-white font-black text-2xl mt-0.5">
                {user.username} <span className="text-white/60 text-lg">さん</span>
              </h1>
              <div className="flex items-center gap-2 mt-1">
                <span className="bg-white/20 text-white text-xs font-black px-2.5 py-0.5 rounded-full">
                  英検 {gradeLabel}
                </span>
                {progress?.trend === 'up' && (
                  <span className="text-xs text-white/80 font-bold">📈 上昇中！</span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              {progress && <StreakBadge streak={progress.streak} />}
              <button
                onClick={() => router.push('/settings')}
                className="w-9 h-9 rounded-2xl bg-white/20 flex items-center justify-center text-white hover:bg-white/30 transition-colors animate-pop-in"
                aria-label="設定"
              >
                ⚙️
              </button>
            </div>
          </div>

          {/* Pass probability + days */}
          <div className="flex items-center justify-between">
            <div className="animate-pop-in delay-200">
              {pct !== null ? (
                <RingProgress pct={pct} />
              ) : (
                <div className="w-32 h-32 rounded-full border-4 border-white/20 flex items-center justify-center">
                  <div className="text-center">
                    <p className="text-white/50 text-2xl font-black">—</p>
                    <p className="text-white/40 text-[10px] font-bold mt-1">まだデータなし</p>
                  </div>
                </div>
              )}
            </div>

            <div className="flex-1 pl-5 animate-slide-up delay-300">
              {days !== null && (
                <div className="mb-4">
                  <div className="inline-flex flex-col items-center bg-white/15 rounded-2xl px-4 py-3 backdrop-blur-sm">
                    <p className="text-white/60 text-[10px] font-bold uppercase tracking-wider">試験まで</p>
                    <p className="text-white font-black text-4xl leading-none">{days}</p>
                    <p className="text-white/60 text-xs font-bold">日</p>
                  </div>
                </div>
              )}
              <button
                onClick={() => router.push('/progress')}
                className="text-white/80 text-xs font-bold flex items-center gap-1 hover:text-white transition-colors"
              >
                詳細を見る <span>→</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Wave divider */}
      <div style={{ marginTop: -2 }}>
        <svg viewBox="0 0 375 30" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ display: 'block', width: '100%' }}>
          <path d="M0 0 C100 30 275 30 375 0 L375 30 L0 30 Z" fill="#7C3AED" opacity="0.15" />
          <path d="M0 10 C120 35 255 25 375 10 L375 30 L0 30 Z" fill="#F5F3FF" />
        </svg>
      </div>

      <div className="max-w-lg mx-auto px-4 pb-8 space-y-5" style={{ marginTop: -8 }}>

        {/* AI praise */}
        {progress?.praise && (
          <div
            className="rounded-3xl p-4 animate-slide-up delay-300"
            style={{ background: 'linear-gradient(135deg, #FEF9C3 0%, #FEF3C7 100%)', border: '1px solid #FDE68A' }}
          >
            <div className="flex gap-3 items-start">
              <span className="text-2xl animate-sparkle">⭐</span>
              <p className="text-amber-800 text-sm font-bold leading-relaxed">{progress.praise}</p>
            </div>
          </div>
        )}

        {/* AI advice */}
        {progress?.advice && (
          <div
            className="rounded-3xl p-4 animate-slide-up delay-400"
            style={{ background: 'linear-gradient(135deg, #EDE9FE 0%, #E0E7FF 100%)', border: '1px solid #C4B5FD' }}
          >
            <p className="text-[10px] font-black text-violet-500 uppercase tracking-wider mb-1">🤖 AIコーチ</p>
            <p className="text-violet-900 text-sm font-semibold leading-relaxed">{progress.advice}</p>
          </div>
        )}

        {/* Flashcard CTA */}
        <button
          onClick={() => router.push('/flashcards')}
          className="w-full rounded-3xl p-5 flex items-center gap-4 text-left animate-slide-up delay-200 hover:scale-[1.02] transition-transform duration-200"
          style={{
            background: 'linear-gradient(135deg, #1E1B4B 0%, #312E81 50%, #4338CA 100%)',
            boxShadow: '0 8px 32px rgba(67,56,202,0.4)',
          }}
        >
          <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-3xl shrink-0 animate-float-slow"
            style={{ background: 'rgba(255,255,255,0.1)' }}>
            🃏
          </div>
          <div className="flex-1">
            <p className="font-black text-white text-base">今日の単語カード</p>
            <p className="text-indigo-300 text-xs font-bold mt-0.5">SM-2 間隔反復 · 科学的暗記法</p>
          </div>
          <div className="text-2xl text-indigo-400 animate-sparkle">✦</div>
        </button>

        {/* Mission cards grid */}
        <div>
          <div className="flex items-center gap-2 mb-3 px-1">
            <div className="w-1 h-5 rounded-full" style={{ background: 'linear-gradient(#7C3AED, #EC4899)' }} />
            <h2 className="font-black text-gray-800 text-sm tracking-wide">4技能ミッション</h2>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {missions.map((card, i) => (
              <MissionCard key={card.skill} card={card} delay={300 + i * 80} />
            ))}
          </div>
        </div>

        {/* Bottom row */}
        <div className="grid grid-cols-2 gap-3">
          <button
            onClick={() => router.push('/mock-exam')}
            className="rounded-3xl p-5 text-left animate-slide-up delay-600 hover:scale-[1.02] transition-transform duration-200"
            style={{
              background: 'linear-gradient(135deg, #1F2937 0%, #374151 100%)',
              boxShadow: '0 4px 20px rgba(0,0,0,0.2)',
            }}
          >
            <div className="text-3xl mb-3 animate-float" style={{ animationDelay: '1s' }}>📝</div>
            <p className="font-black text-white text-sm">模擬試験</p>
            <p className="text-gray-400 text-[10px] font-bold mt-0.5">4技能 · 本番形式</p>
          </button>

          <button
            onClick={() => router.push('/vocabulary')}
            className="rounded-3xl p-5 text-left animate-slide-up delay-700 hover:scale-[1.02] transition-transform duration-200"
            style={{
              background: 'linear-gradient(135deg, #5B21B6 0%, #7C3AED 50%, #A855F7 100%)',
              boxShadow: '0 4px 20px rgba(124,58,237,0.4)',
            }}
          >
            <div className="text-3xl mb-3 animate-float" style={{ animationDelay: '1.4s' }}>🔗</div>
            <p className="font-black text-white text-sm">語彙ネット</p>
            <p className="text-purple-300 text-[10px] font-bold mt-0.5">語根クラスター</p>
          </button>
        </div>

        {/* Logout */}
        <div className="flex justify-center pt-2">
          <button
            onClick={logout}
            className="text-gray-400 text-xs font-bold hover:text-gray-600 transition-colors px-4 py-2"
          >
            ログアウト
          </button>
        </div>
      </div>
    </main>
  )
}
