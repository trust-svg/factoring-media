'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiCreateFlashcard, apiGetVocabClusters } from '@/lib/api'
import { useAuth } from '@/providers/AuthProvider'
import type { VocabCluster, VocabMember } from '@/lib/types'

type GradeFilter = 'all' | 'pre2' | '2'

function MemberRow({
  member,
  added,
  onAdd,
}: {
  member: VocabMember
  added: boolean
  onAdd: () => void
}) {
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-gray-50 last:border-0">
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="font-bold text-gray-800 text-sm">{member.word}</span>
          <span className="text-xs text-gray-400 italic">{member.pos}</span>
          <span className="text-xs text-gray-600">{member.meaning}</span>
        </div>
        <p className="text-xs text-gray-400 mt-0.5 italic">{member.example}</p>
      </div>
      <button
        onClick={onAdd}
        disabled={added}
        className={`shrink-0 text-xs px-2.5 py-1 rounded-lg font-medium transition-colors ${
          added
            ? 'bg-green-100 text-green-600 cursor-default'
            : 'bg-indigo-50 text-indigo-600 hover:bg-indigo-100'
        }`}
      >
        {added ? '追加済み' : '+ カード'}
      </button>
    </div>
  )
}

function ClusterCard({ cluster }: { cluster: VocabCluster }) {
  const [open, setOpen] = useState(false)
  const [added, setAdded] = useState<Set<string>>(new Set())
  const [adding, setAdding] = useState<string | null>(null)

  const handleAdd = async (member: VocabMember) => {
    if (added.has(member.word) || adding) return
    setAdding(member.word)
    try {
      await apiCreateFlashcard(member.word, `${member.meaning}\n例: ${member.example}`)
      setAdded((prev) => new Set([...prev, member.word]))
    } catch {
      // non-fatal — user can retry
    } finally {
      setAdding(null)
    }
  }

  const addedCount = added.size
  const total = cluster.members.length

  return (
    <div className="bg-white rounded-2xl shadow-sm overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full px-4 py-4 flex items-center gap-3 text-left"
      >
        <div
          className="w-1 self-stretch rounded-full shrink-0"
          style={{ backgroundColor: cluster.color }}
        />
        <div className="flex-1 min-w-0">
          <p className="font-bold text-gray-800 text-sm">{cluster.root}</p>
          <p className="text-xs text-gray-400 mt-0.5">
            {total}語
            {addedCount > 0 && (
              <span className="ml-2 text-green-500">{addedCount}枚追加済み</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span
            className="text-xs px-2 py-0.5 rounded-full font-medium"
            style={{
              backgroundColor: `${cluster.color}20`,
              color: cluster.color,
            }}
          >
            {cluster.grade === 'pre2' ? '準2級' : '2級'}
          </span>
          <span className={`text-gray-400 text-lg transition-transform ${open ? 'rotate-180' : ''}`}>
            ⌄
          </span>
        </div>
      </button>

      {open && (
        <div className="px-4 pb-4">
          <div className="border-t border-gray-50 pt-2">
            {cluster.members.map((m) => (
              <MemberRow
                key={m.word}
                member={m}
                added={added.has(m.word)}
                onAdd={() => handleAdd(m)}
              />
            ))}
          </div>
          {total > 0 && addedCount < total && (
            <button
              onClick={async () => {
                for (const m of cluster.members) {
                  if (!added.has(m.word)) await handleAdd(m).catch(() => {})
                }
              }}
              className="mt-3 w-full text-xs bg-indigo-50 text-indigo-600 hover:bg-indigo-100 py-2 rounded-xl font-medium transition-colors"
            >
              全{total}語をカードに追加
            </button>
          )}
          {addedCount === total && (
            <p className="mt-3 text-center text-xs text-green-500 font-medium">
              このクラスターの全語を追加しました！
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export default function VocabularyPage() {
  const router = useRouter()
  const { user } = useAuth()
  const [clusters, setClusters] = useState<VocabCluster[]>([])
  const [loading, setLoading] = useState(true)
  const [gradeFilter, setGradeFilter] = useState<GradeFilter>('all')
  const [search, setSearch] = useState('')

  useEffect(() => {
    apiGetVocabClusters()
      .then((res) => setClusters(res.clusters))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  // Default grade filter to user's grade
  useEffect(() => {
    if (user?.grade) setGradeFilter(user.grade as GradeFilter)
  }, [user])

  const filtered = clusters.filter((c) => {
    if (gradeFilter !== 'all' && c.grade !== gradeFilter) return false
    if (search) {
      const q = search.toLowerCase()
      return (
        c.root.toLowerCase().includes(q) ||
        c.members.some(
          (m) => m.word.toLowerCase().includes(q) || m.meaning.includes(q),
        )
      )
    }
    return true
  })

  return (
    <main className="min-h-screen bg-indigo-50">
      {/* Header */}
      <div className="bg-white px-4 pt-4 pb-3 shadow-sm flex items-center gap-3">
        <button onClick={() => router.back()} className="text-gray-400 text-xl px-1">
          ‹
        </button>
        <div>
          <h1 className="font-bold text-gray-800">語彙ネットワーク</h1>
          <p className="text-xs text-gray-400">語根でつながる英単語クラスター</p>
        </div>
      </div>

      {/* Filter bar */}
      <div className="bg-white border-b border-gray-100 px-4 py-3 space-y-2">
        {/* Grade tabs */}
        <div className="flex gap-2">
          {([['all', 'すべて'], ['pre2', '準2級'], ['2', '2級']] as const).map(([val, label]) => (
            <button
              key={val}
              onClick={() => setGradeFilter(val)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                gradeFilter === val
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        {/* Search */}
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="単語・意味で検索..."
          className="w-full text-sm bg-gray-50 border border-gray-100 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />
      </div>

      <div className="max-w-lg mx-auto px-4 py-4 space-y-3">
        {loading && (
          <p className="text-center text-gray-400 text-sm py-10">読み込み中...</p>
        )}

        {!loading && filtered.length === 0 && (
          <div className="text-center py-10">
            <p className="text-gray-400 text-sm">該当するクラスターがありません</p>
            {search && (
              <button
                onClick={() => setSearch('')}
                className="mt-2 text-indigo-500 text-xs underline"
              >
                検索をリセット
              </button>
            )}
          </div>
        )}

        {!loading && (
          <p className="text-xs text-gray-400 px-1">
            {filtered.length}クラスター ·{' '}
            {filtered.reduce((s, c) => s + c.members.length, 0)}語
          </p>
        )}

        {filtered.map((cluster) => (
          <ClusterCard key={cluster.id} cluster={cluster} />
        ))}

        {!loading && filtered.length > 0 && (
          <div className="bg-indigo-50 border border-indigo-100 rounded-2xl p-4 mt-2">
            <p className="text-xs text-indigo-600 leading-relaxed">
              💡 気に入った単語は「+ カード」で単語カードに追加できます。
              追加後は <strong>フラッシュカード</strong> で SM-2 間隔反復が始まります。
            </p>
          </div>
        )}
      </div>
    </main>
  )
}
