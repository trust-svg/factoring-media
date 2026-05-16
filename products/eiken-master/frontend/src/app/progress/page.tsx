'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiGetProgress } from '@/lib/api'
import type { ProgressData } from '@/lib/types'

const SKILL_LABELS: Record<string, string> = {
  reading: 'リーディング',
  listening: 'リスニング',
  writing: 'ライティング',
  speaking: 'スピーキング',
}
const SKILL_COLORS: Record<string, string> = {
  reading: '#3b82f6',
  listening: '#22c55e',
  writing: '#f59e0b',
  speaking: '#f43f5e',
}

// SVG radar chart for 4 skills arranged as diamond (top/right/bottom/left)
function RadarChart({ breakdown }: { breakdown: ProgressData['skill_breakdown'] }) {
  const cx = 110
  const cy = 110
  const r = 80
  const skills = ['reading', 'listening', 'writing', 'speaking'] as const
  // Angles: reading=top(-90°), listening=right(0°), writing=bottom(90°), speaking=left(180°)
  const angles = [-Math.PI / 2, 0, Math.PI / 2, Math.PI]

  const toPoint = (angle: number, value: number) => ({
    x: cx + r * value * Math.cos(angle),
    y: cy + r * value * Math.sin(angle),
  })

  const gridLevels = [0.25, 0.5, 0.75, 1.0]
  const gridPoints = (level: number) =>
    angles.map((a) => toPoint(a, level)).map((p) => `${p.x},${p.y}`).join(' ')

  const dataPoints = skills
    .map((s, i) => toPoint(angles[i], breakdown[s] ?? 0))
    .map((p) => `${p.x},${p.y}`)
    .join(' ')

  const axisLabels = [
    { angle: angles[0], label: 'リーディング', offset: { x: 0, y: -12 } },
    { angle: angles[1], label: 'リスニング', offset: { x: 14, y: 4 } },
    { angle: angles[2], label: 'ライティング', offset: { x: 0, y: 14 } },
    { angle: angles[3], label: 'スピーキング', offset: { x: -14, y: 4 } },
  ]

  return (
    <svg viewBox="0 0 220 220" className="w-full max-w-xs mx-auto">
      {/* Grid */}
      {gridLevels.map((lv) => (
        <polygon
          key={lv}
          points={gridPoints(lv)}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth={1}
        />
      ))}
      {/* Axes */}
      {angles.map((a, i) => {
        const end = toPoint(a, 1)
        return (
          <line key={i} x1={cx} y1={cy} x2={end.x} y2={end.y} stroke="#e5e7eb" strokeWidth={1} />
        )
      })}
      {/* Data polygon */}
      <polygon points={dataPoints} fill="#6366f1" fillOpacity={0.3} stroke="#6366f1" strokeWidth={2} />
      {/* Data dots */}
      {skills.map((s, i) => {
        const p = toPoint(angles[i], breakdown[s] ?? 0)
        return <circle key={s} cx={p.x} cy={p.y} r={4} fill="#6366f1" />
      })}
      {/* Labels */}
      {axisLabels.map(({ angle, label, offset }) => {
        const end = toPoint(angle, 1)
        return (
          <text
            key={label}
            x={end.x + offset.x}
            y={end.y + offset.y}
            textAnchor="middle"
            fontSize={9}
            fill="#6b7280"
          >
            {label}
          </text>
        )
      })}
      {/* Center % labels */}
      {skills.map((s, i) => {
        const v = breakdown[s]
        if (v === null) return null
        const p = toPoint(angles[i], v)
        return (
          <text key={`pct-${s}`} x={p.x} y={p.y - 7} textAnchor="middle" fontSize={8} fill="#4338ca" fontWeight="bold">
            {Math.round(v * 100)}%
          </text>
        )
      })}
    </svg>
  )
}

export default function ProgressPage() {
  const router = useRouter()
  const [data, setData] = useState<ProgressData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiGetProgress()
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-indigo-50">
        <p className="text-indigo-400 text-sm">読み込み中...</p>
      </div>
    )
  }

  const gradeLabel = data?.grade === 'pre2' ? '準2級' : '2級'
  const probPct = data?.pass_probability != null ? Math.round(data.pass_probability * 100) : null
  const trendIcon = data?.trend === 'up' ? '↑' : data?.trend === 'down' ? '↓' : '→'
  const trendColor = data?.trend === 'up' ? 'text-green-600' : data?.trend === 'down' ? 'text-red-500' : 'text-gray-400'

  return (
    <main className="min-h-screen bg-indigo-50">
      <div className="bg-white px-4 pt-4 pb-3 shadow-sm flex items-center gap-3">
        <button onClick={() => router.back()} className="text-gray-400 text-xl px-1">‹</button>
        <h1 className="font-bold text-gray-800">学習進捗</h1>
      </div>

      <div className="max-w-sm mx-auto px-4 py-5 space-y-4">
        {/* Pass probability */}
        <div className="bg-white rounded-2xl p-5 shadow-sm text-center">
          <p className="text-xs text-gray-400 mb-1">英検{gradeLabel} 合格確率</p>
          {probPct != null ? (
            <>
              <p className={`text-5xl font-bold ${probPct >= 70 ? 'text-green-600' : probPct >= 50 ? 'text-amber-500' : 'text-red-500'}`}>
                {probPct}%
              </p>
              <div className="w-full bg-gray-100 rounded-full h-2.5 mt-3">
                <div
                  className={`h-2.5 rounded-full transition-all ${probPct >= 70 ? 'bg-green-500' : probPct >= 50 ? 'bg-amber-400' : 'bg-red-400'}`}
                  style={{ width: `${probPct}%` }}
                />
              </div>
              <p className={`text-sm mt-2 font-semibold ${trendColor}`}>
                {trendIcon} {data?.trend === 'up' ? '上昇中' : data?.trend === 'down' ? '下降中' : '横ばい'}
              </p>
            </>
          ) : (
            <p className="text-gray-400 text-sm mt-2">まだデータがありません。学習を始めましょう！</p>
          )}
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-white rounded-2xl p-4 shadow-sm text-center">
            <p className="text-2xl font-bold text-indigo-600">{data?.streak ?? 0}</p>
            <p className="text-xs text-gray-400 mt-0.5">連続日数</p>
          </div>
          <div className="bg-white rounded-2xl p-4 shadow-sm text-center">
            <p className="text-2xl font-bold text-indigo-600">{data?.total_sessions ?? 0}</p>
            <p className="text-xs text-gray-400 mt-0.5">総セッション</p>
          </div>
          <div className="bg-white rounded-2xl p-4 shadow-sm text-center">
            <p className="text-2xl font-bold text-indigo-600">{data?.days_remaining ?? '—'}</p>
            <p className="text-xs text-gray-400 mt-0.5">試験まで</p>
          </div>
        </div>

        {/* Radar chart */}
        {data && (
          <div className="bg-white rounded-2xl p-5 shadow-sm">
            <p className="text-xs text-gray-400 mb-3">スキル別正答率（直近14日）</p>
            <RadarChart breakdown={data.skill_breakdown} />
          </div>
        )}

        {/* Skill bars */}
        {data && (
          <div className="bg-white rounded-2xl p-5 shadow-sm space-y-3">
            <p className="text-xs text-gray-400">スキル詳細</p>
            {(['reading', 'listening', 'writing', 'speaking'] as const).map((skill) => {
              const v = data.skill_breakdown[skill]
              return (
                <div key={skill}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-gray-600">{SKILL_LABELS[skill]}</span>
                    <span className="font-bold text-gray-700">
                      {v != null ? `${Math.round(v * 100)}%` : 'データなし'}
                    </span>
                  </div>
                  <div className="w-full bg-gray-100 rounded-full h-2">
                    <div
                      className="h-2 rounded-full"
                      style={{ width: `${v != null ? Math.round(v * 100) : 0}%`, backgroundColor: SKILL_COLORS[skill] }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* AI Advice */}
        {data?.advice && (
          <div className="bg-indigo-50 border border-indigo-200 rounded-2xl p-4">
            <p className="text-xs text-indigo-400 mb-1">AIコーチからのアドバイス</p>
            <p className="text-sm text-indigo-800 leading-relaxed">{data.advice}</p>
          </div>
        )}
      </div>
    </main>
  )
}
