import { prisma } from "@/lib/prisma";
import { CompanyCard } from "@/components/CompanyCard";

export const dynamic = "force-dynamic";

const medalColors = [
  { bg: "bg-amber-400", text: "text-amber-900", label: "No.1", border: "border-amber-400" },
  { bg: "bg-gray-300", text: "text-gray-700", label: "No.2", border: "border-gray-300" },
  { bg: "bg-orange-400", text: "text-orange-900", label: "No.3", border: "border-orange-400" },
];

const industries = [
  {
    name: "建設業",
    href: "/industry/construction",
    icon: (
      <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
      </svg>
    ),
    desc: "工事代金の入金サイクルが長い建設業に最適",
  },
  {
    name: "運送業",
    href: "/industry/transport",
    icon: (
      <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10a1 1 0 001 1h1m8-1a1 1 0 01-1 1H9m4-1V8a1 1 0 011-1h2.586a1 1 0 01.707.293l3.414 3.414a1 1 0 01.293.707V16a1 1 0 01-1 1h-1m-6-1a1 1 0 001 1h1M5 17a2 2 0 104 0m-4 0a2 2 0 114 0m6 0a2 2 0 104 0m-4 0a2 2 0 114 0" />
      </svg>
    ),
    desc: "燃料費・車両維持費の資金繰りをサポート",
  },
  {
    name: "IT・フリーランス",
    href: "/industry/it-freelance",
    icon: (
      <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    ),
    desc: "少額債権もOK、個人でも利用しやすい",
  },
  {
    name: "医療・介護",
    href: "/industry/medical",
    icon: (
      <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
      </svg>
    ),
    desc: "診療報酬債権の早期現金化が可能",
  },
  {
    name: "個人事業主",
    href: "/industry/sole-proprietor",
    icon: (
      <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    ),
    desc: "法人でなくても利用できる業者を厳選",
  },
];

export default async function HomePage() {
  const topCompanies = await prisma.company.findMany({
    where: { isRecommended: true },
    orderBy: { rankingOrder: "asc" },
    take: 3,
  });

  const top5Companies = await prisma.company.findMany({
    where: { rankingOrder: { not: null } },
    orderBy: { rankingOrder: "asc" },
    take: 5,
  });

  const latestReviews = await prisma.review.findMany({
    where: { isApproved: true },
    orderBy: { createdAt: "desc" },
    take: 3,
    include: { company: { select: { name: true, slug: true } } },
  });

  return (
    <>
      {/* ==================== 1. Hero Section ==================== */}
      <section className="bg-gradient-to-br from-primary-darker via-primary-dark to-primary text-white overflow-hidden">
        <div className="max-w-6xl mx-auto px-4 py-14 md:py-20 flex flex-col md:flex-row items-center gap-8">
          <div className="flex-1 text-center md:text-left">
            <div className="inline-block bg-white/10 backdrop-blur-sm px-4 py-1.5 rounded-full text-sm mb-4">
              <span className="text-accent font-bold">2026年3月</span> 最新ランキング公開中
            </div>
            <h1 className="text-3xl md:text-5xl font-black leading-tight mb-4">
              ファクタリング業者を
              <br />
              <span className="text-secondary-light">口コミ・評判</span>で
              <br className="md:hidden" />
              徹底比較
            </h1>
            <p className="text-blue-200 text-lg mb-6 max-w-lg">
              手数料・入金速度・審査基準を実際の利用者の声で比較。
              <br className="hidden md:block" />
              あなたに最適な業者が見つかります。
            </p>
            <div className="flex flex-col sm:flex-row gap-3 justify-center md:justify-start mb-8">
              <a
                href="/estimate"
                className="bg-cta hover:bg-cta-dark text-white px-8 py-4 rounded-xl text-lg font-bold transition-colors shadow-lg pulse-cta"
              >
                無料で一括見積もり
              </a>
              <a
                href="/ranking"
                className="bg-white/10 hover:bg-white/20 text-white px-8 py-4 rounded-xl text-lg font-medium transition-colors border border-white/20"
              >
                ランキングを見る
              </a>
            </div>
            {/* Stats */}
            <div className="flex gap-6 justify-center md:justify-start">
              <div className="text-center">
                <p className="text-3xl font-black text-white">
                  10<span className="text-lg">社</span>
                </p>
                <p className="text-xs text-blue-300">掲載業者数</p>
              </div>
              <div className="w-px bg-white/20" />
              <div className="text-center">
                <p className="text-3xl font-black text-white">
                  96<span className="text-lg">%</span>
                </p>
                <p className="text-xs text-blue-300">利用満足度</p>
              </div>
              <div className="w-px bg-white/20" />
              <div className="text-center">
                <p className="text-3xl font-black text-white">
                  最短<span className="text-lg">10分</span>
                </p>
                <p className="text-xs text-blue-300">入金スピード</p>
              </div>
            </div>
          </div>

          {/* Hero illustration - business person */}
          <div className="flex-1 hidden md:flex justify-center">
            <svg
              width="360"
              height="360"
              viewBox="0 0 400 400"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              {/* Background circles */}
              <circle cx="200" cy="200" r="180" fill="white" fillOpacity="0.05" />
              <circle cx="200" cy="200" r="140" fill="white" fillOpacity="0.05" />
              {/* Person body */}
              <rect x="150" y="160" width="100" height="130" rx="8" fill="#3b82f6" />
              {/* Shirt/tie */}
              <rect x="180" y="160" width="40" height="60" fill="white" fillOpacity="0.9" />
              <polygon points="200,160 190,190 210,190" fill="#1e40af" />
              {/* Head */}
              <circle cx="200" cy="130" r="40" fill="#fbbf24" fillOpacity="0.2" />
              <circle cx="200" cy="130" r="35" fill="#fed7aa" />
              {/* Hair */}
              <ellipse cx="200" cy="110" rx="38" ry="20" fill="#374151" />
              {/* Eyes */}
              <circle cx="188" cy="128" r="3" fill="#1e293b" />
              <circle cx="212" cy="128" r="3" fill="#1e293b" />
              {/* Smile */}
              <path
                d="M192 140 Q200 148 208 140"
                stroke="#1e293b"
                strokeWidth="2"
                fill="none"
                strokeLinecap="round"
              />
              {/* Arms */}
              <rect x="110" y="170" width="45" height="16" rx="8" fill="#3b82f6" />
              <rect x="245" y="170" width="45" height="16" rx="8" fill="#3b82f6" />
              {/* Document in hand */}
              <rect x="270" y="145" width="50" height="65" rx="4" fill="white" />
              <rect x="278" y="155" width="34" height="3" rx="1" fill="#93c5fd" />
              <rect x="278" y="163" width="34" height="3" rx="1" fill="#93c5fd" />
              <rect x="278" y="171" width="24" height="3" rx="1" fill="#93c5fd" />
              <rect
                x="278"
                y="185"
                width="34"
                height="10"
                rx="2"
                fill="#10b981"
                fillOpacity="0.3"
              />
              <text x="285" y="193" fill="#10b981" fontSize="8" fontWeight="bold">
                OK
              </text>
              {/* Legs */}
              <rect x="165" y="285" width="30" height="50" rx="4" fill="#1e3a8a" />
              <rect x="205" y="285" width="30" height="50" rx="4" fill="#1e3a8a" />
              {/* Shoes */}
              <rect x="160" y="330" width="40" height="12" rx="6" fill="#0f172a" />
              <rect x="200" y="330" width="40" height="12" rx="6" fill="#0f172a" />
              {/* Floating elements */}
              <rect x="60" y="100" width="50" height="35" rx="6" fill="white" fillOpacity="0.1" />
              <text x="72" y="115" fill="white" fillOpacity="0.6" fontSize="8">
                ¥
              </text>
              <text x="68" y="128" fill="white" fillOpacity="0.4" fontSize="7">
                即日
              </text>
              <rect x="300" y="80" width="55" height="35" rx="6" fill="white" fillOpacity="0.1" />
              <text x="310" y="95" fill="#fbbf24" fontSize="10">
                ★★★
              </text>
              <text x="310" y="108" fill="white" fillOpacity="0.4" fontSize="7">
                4.5
              </text>
              <rect x="80" y="260" width="50" height="35" rx="6" fill="white" fillOpacity="0.1" />
              <text x="92" y="280" fill="white" fillOpacity="0.6" fontSize="10">
                比較
              </text>
            </svg>
          </div>
        </div>
      </section>

      {/* ==================== 2. Trust Bar ==================== */}
      <section className="bg-white border-b border-gray-100 py-4">
        <div className="max-w-6xl mx-auto px-4">
          <div className="flex flex-wrap items-center justify-center gap-6 md:gap-10 text-sm text-gray-500">
            <div className="flex items-center gap-2">
              <svg className="w-5 h-5 text-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>完全無料で利用可能</span>
            </div>
            <div className="flex items-center gap-2">
              <svg className="w-5 h-5 text-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>厳選された優良業者のみ掲載</span>
            </div>
            <div className="flex items-center gap-2">
              <svg className="w-5 h-5 text-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>最新情報を定期更新</span>
            </div>
          </div>
        </div>
      </section>

      {/* ==================== Quick Comparison Table ==================== */}
      <section className="max-w-4xl mx-auto px-4 -mt-8 relative z-10 mb-12">
        <div className="bg-white rounded-2xl shadow-lg border border-gray-100 overflow-hidden">
          <div className="bg-gradient-to-r from-primary to-primary-light text-white px-6 py-3 flex items-center gap-2">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
            <h2 className="font-bold">TOP5 ファクタリング業者 早見表【2026年3月最新】</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="px-4 py-3 text-left font-medium text-gray-600">順位</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">業者名</th>
                  <th className="px-4 py-3 text-center font-medium text-gray-600">手数料</th>
                  <th className="px-4 py-3 text-center font-medium text-gray-600">入金速度</th>
                  <th className="px-4 py-3 text-center font-medium text-gray-600">評価</th>
                  <th className="px-4 py-3 text-center font-medium text-gray-600">詳細</th>
                </tr>
              </thead>
              <tbody>
                {top5Companies.map((c, i) => (
                  <tr key={c.slug} className={`border-b border-gray-100 ${i === 0 ? "bg-amber-50/50" : ""}`}>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center justify-center w-7 h-7 rounded-full text-xs font-black ${
                        i === 0 ? "bg-amber-400 text-amber-900" :
                        i === 1 ? "bg-gray-300 text-gray-700" :
                        i === 2 ? "bg-amber-600 text-white" :
                        "bg-primary/10 text-primary"
                      }`}>{i + 1}</span>
                    </td>
                    <td className="px-4 py-3 font-bold text-primary-darker whitespace-nowrap">{c.name}</td>
                    <td className="px-4 py-3 text-center font-bold whitespace-nowrap">{c.fee || "-"}</td>
                    <td className="px-4 py-3 text-center whitespace-nowrap">{c.depositSpeed || "-"}</td>
                    <td className="px-4 py-3 text-center">
                      <span className="text-star font-bold">{c.rating?.toFixed(1) || "-"}</span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <a href={`/companies/${c.slug}`} className="inline-block bg-cta text-white text-xs px-3 py-1.5 rounded font-bold hover:bg-cta-dark transition-colors whitespace-nowrap">
                        詳細 →
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* ==================== 3. TOP3 Ranking ==================== */}
      <section className="max-w-6xl mx-auto px-4 py-16">
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 bg-primary/5 px-4 py-1.5 rounded-full mb-4">
            <svg className="w-5 h-5 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
            </svg>
            <span className="text-primary font-bold text-sm">厳選ランキング</span>
          </div>
          <h2 className="text-2xl md:text-3xl font-bold text-primary-dark mb-3">
            おすすめファクタリング業者 TOP3
          </h2>
          <p className="text-gray-500">
            2026年3月最新版 -- 口コミ・手数料・入金速度を総合評価
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {topCompanies.map((company, index) => (
            <div key={company.slug} className="relative">
              {/* Medal badge */}
              {index < 3 && (
                <div
                  className={`absolute -top-3 left-4 z-10 ${medalColors[index].bg} ${medalColors[index].text} text-xs font-black px-3 py-1 rounded-full shadow-md`}
                >
                  {medalColors[index].label}
                </div>
              )}
              <CompanyCard {...company} />
            </div>
          ))}
        </div>

        <div className="text-center mt-8">
          <a
            href="/ranking"
            className="inline-flex items-center gap-1 text-primary font-bold hover:underline"
          >
            全ランキングを見る
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </a>
        </div>
      </section>

      {/* ==================== 4. What is Factoring ==================== */}
      <section className="bg-gray-50 py-16">
        <div className="max-w-6xl mx-auto px-4">
          <h2 className="text-2xl md:text-3xl font-bold text-primary-dark mb-10 text-center">
            ファクタリングとは?
          </h2>

          <div className="flex flex-col md:flex-row items-center gap-10 mb-10">
            {/* Text */}
            <div className="flex-1">
              <p className="text-gray-700 leading-relaxed mb-4">
                ファクタリングとは、企業が保有する売掛金（請求書）をファクタリング会社に売却して、
                支払期日前に現金化する資金調達方法です。
              </p>
              <p className="text-gray-700 leading-relaxed">
                融資とは異なり<strong>借入ではない</strong>ため、信用情報に影響せず、
                最短即日で資金を得ることができます。
              </p>
            </div>

            {/* Flow diagram SVG */}
            <div className="flex-1 flex justify-center">
              <svg
                width="340"
                height="200"
                viewBox="0 0 340 200"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                className="max-w-full"
              >
                {/* Your Company */}
                <rect x="0" y="60" width="90" height="80" rx="10" fill="#1e40af" />
                <text x="45" y="95" fill="white" fontSize="11" fontWeight="bold" textAnchor="middle">
                  あなたの
                </text>
                <text x="45" y="112" fill="white" fontSize="11" fontWeight="bold" textAnchor="middle">
                  会社
                </text>
                {/* Arrow 1 */}
                <path d="M95 90 L125 90" stroke="#3b82f6" strokeWidth="3" markerEnd="url(#arrowhead)" />
                <text x="110" y="82" fill="#3b82f6" fontSize="8" textAnchor="middle">
                  売掛金
                </text>
                {/* Factoring Company */}
                <rect x="130" y="50" width="90" height="100" rx="10" fill="#0ea5e9" />
                <text x="175" y="90" fill="white" fontSize="10" fontWeight="bold" textAnchor="middle">
                  ファクタリング
                </text>
                <text x="175" y="106" fill="white" fontSize="10" fontWeight="bold" textAnchor="middle">
                  業者
                </text>
                {/* Arrow 2 */}
                <path d="M130 130 L95 130" stroke="#10b981" strokeWidth="3" markerEnd="url(#arrowhead-green)" />
                <text x="110" y="148" fill="#10b981" fontSize="8" textAnchor="middle" fontWeight="bold">
                  即日入金
                </text>
                {/* Arrow 3 */}
                <path d="M225 100 L255 100" stroke="#3b82f6" strokeWidth="3" markerEnd="url(#arrowhead)" />
                <text x="240" y="92" fill="#3b82f6" fontSize="8" textAnchor="middle">
                  回収
                </text>
                {/* Client Company */}
                <rect x="260" y="60" width="80" height="80" rx="10" fill="#64748b" />
                <text x="300" y="95" fill="white" fontSize="11" fontWeight="bold" textAnchor="middle">
                  取引先
                </text>
                <text x="300" y="112" fill="white" fontSize="11" fontWeight="bold" textAnchor="middle">
                  企業
                </text>
                {/* Arrow markers */}
                <defs>
                  <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
                    <polygon points="0 0, 10 3.5, 0 7" fill="#3b82f6" />
                  </marker>
                  <marker id="arrowhead-green" markerWidth="10" markerHeight="7" refX="0" refY="3.5" orient="auto">
                    <polygon points="10 0, 0 3.5, 10 7" fill="#10b981" />
                  </marker>
                </defs>
              </svg>
            </div>
          </div>

          {/* 3 Merit Cards */}
          <div className="grid md:grid-cols-3 gap-5">
            <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 card-hover">
              <div className="w-12 h-12 bg-green/10 rounded-xl flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h3 className="font-bold text-primary-dark mb-2">最短即日入金</h3>
              <p className="text-sm text-gray-600">
                申込みから最短即日で現金化。急な資金需要にも対応できます。
              </p>
            </div>
            <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 card-hover">
              <div className="w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <h3 className="font-bold text-primary-dark mb-2">借入ではない</h3>
              <p className="text-sm text-gray-600">
                売掛金の売却なので借入に該当せず、信用情報に影響しません。
              </p>
            </div>
            <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 card-hover">
              <div className="w-12 h-12 bg-accent/10 rounded-xl flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
              </div>
              <h3 className="font-bold text-primary-dark mb-2">赤字でもOK</h3>
              <p className="text-sm text-gray-600">
                審査は売掛先の信用力がベース。自社の業績に関わらず利用可能です。
              </p>
            </div>
          </div>

          <div className="text-center mt-8">
            <a
              href="/articles/what-is-factoring"
              className="inline-flex items-center gap-1 text-primary font-medium hover:underline"
            >
              ファクタリングについてもっと詳しく
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </a>
          </div>
        </div>
      </section>

      {/* ==================== 5. Pain Points ==================== */}
      <section className="py-16 bg-white">
        <div className="max-w-4xl mx-auto px-4">
          <h2 className="text-2xl md:text-3xl font-bold text-primary-dark mb-10 text-center">
            こんなお悩みありませんか?
          </h2>

          <div className="space-y-5 mb-10">
            {/* Pain 1 */}
            <div className="flex items-start gap-4">
              <div className="shrink-0 w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center">
                <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </div>
              <div className="flex-1 bg-gray-50 rounded-2xl rounded-tl-sm px-5 py-4 border border-gray-100">
                <p className="text-gray-700 font-medium">
                  売掛金の入金が2ヶ月後で資金繰りが厳しい...
                </p>
              </div>
            </div>
            {/* Pain 2 */}
            <div className="flex items-start gap-4">
              <div className="shrink-0 w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center">
                <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </div>
              <div className="flex-1 bg-gray-50 rounded-2xl rounded-tl-sm px-5 py-4 border border-gray-100">
                <p className="text-gray-700 font-medium">
                  銀行融資の審査に落ちてしまった...
                </p>
              </div>
            </div>
            {/* Pain 3 */}
            <div className="flex items-start gap-4">
              <div className="shrink-0 w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center">
                <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </div>
              <div className="flex-1 bg-gray-50 rounded-2xl rounded-tl-sm px-5 py-4 border border-gray-100">
                <p className="text-gray-700 font-medium">
                  急な出費で今すぐ現金が必要...
                </p>
              </div>
            </div>
          </div>

          {/* Solution */}
          <div className="relative">
            <div className="absolute left-1/2 -translate-x-1/2 -top-4">
              <svg className="w-8 h-8 text-primary" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2l-2 7H3l6 4.5L7 21l5-3.5L17 21l-2-7.5L21 9h-7z" />
              </svg>
            </div>
            <div className="bg-gradient-to-r from-primary to-secondary rounded-2xl p-6 md:p-8 text-center text-white">
              <h3 className="text-xl md:text-2xl font-bold mb-3">
                ファクタリングで解決できます!
              </h3>
              <p className="text-blue-100 mb-5">
                売掛金を即日現金化。借入ではないので信用情報にも影響しません。
              </p>
              <a
                href="/estimate"
                className="inline-block bg-cta hover:bg-cta-dark text-white px-8 py-3.5 rounded-xl font-bold transition-colors shadow-lg pulse-cta"
              >
                無料で相談してみる
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* ==================== 6. Industry Recommendations ==================== */}
      <section className="bg-gray-50 py-16">
        <div className="max-w-6xl mx-auto px-4">
          <h2 className="text-2xl md:text-3xl font-bold text-primary-dark mb-3 text-center">
            業種別おすすめファクタリング
          </h2>
          <p className="text-gray-500 text-center mb-10">
            業種ごとに最適なファクタリング業者をご紹介
          </p>

          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {industries.map((industry) => (
              <a
                key={industry.name}
                href={industry.href}
                className="bg-white rounded-xl p-5 text-center border border-gray-100 hover:border-primary/30 hover:shadow-md transition-all group"
              >
                <div className="w-14 h-14 mx-auto bg-primary/5 group-hover:bg-primary/10 rounded-xl flex items-center justify-center text-primary mb-3 transition-colors">
                  {industry.icon}
                </div>
                <h3 className="font-bold text-primary-dark text-sm mb-1">{industry.name}</h3>
                <p className="text-xs text-gray-500 leading-relaxed">{industry.desc}</p>
              </a>
            ))}
          </div>
        </div>
      </section>

      {/* ==================== 7. Latest Reviews ==================== */}
      {latestReviews.length > 0 && (
        <section className="max-w-6xl mx-auto px-4 py-16">
          <div className="text-center mb-10">
            <h2 className="text-2xl md:text-3xl font-bold text-primary-dark mb-3">
              最新の口コミ
            </h2>
            <p className="text-gray-500">実際に利用した方のリアルな声をお届けします</p>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {latestReviews.map((review) => (
              <div
                key={review.id}
                className="bg-white border border-gray-200 rounded-xl p-5 card-hover"
              >
                <div className="flex items-center gap-2 mb-3">
                  <div className="flex text-star">
                    {Array.from({ length: review.rating }).map((_, i) => (
                      <span key={i}>&#9733;</span>
                    ))}
                  </div>
                  <span className="text-xs text-gray-400">
                    {review.createdAt.toLocaleDateString("ja-JP")}
                  </span>
                </div>
                <h3 className="font-bold text-primary-dark mb-2">{review.title}</h3>
                <p className="text-sm text-gray-600 line-clamp-3 mb-3">{review.body}</p>
                <a
                  href={`/companies/${review.company.slug}`}
                  className="inline-flex items-center gap-1 text-sm text-primary font-medium hover:underline"
                >
                  {review.company.name}の詳細
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </a>
              </div>
            ))}
          </div>

          <div className="text-center mt-8">
            <a
              href="/reviews"
              className="inline-flex items-center gap-1 text-primary font-bold hover:underline"
            >
              すべての口コミを見る
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </a>
          </div>
        </section>
      )}

      {/* ==================== Supervisor Section ==================== */}
      <section className="max-w-4xl mx-auto px-4 py-12">
        <div className="bg-white rounded-2xl border border-gray-200 p-6 md:p-8">
          <h2 className="text-lg font-bold text-primary-darker mb-6 flex items-center gap-2">
            <svg className="w-5 h-5 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
            当サイトの監修者
          </h2>
          <div className="flex flex-col md:flex-row gap-6">
            <div className="flex gap-4 flex-1">
              <div className="w-16 h-16 bg-gradient-to-br from-primary to-primary-light rounded-full flex items-center justify-center shrink-0 shadow-md">
                <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </div>
              <div>
                <p className="font-bold text-primary-darker">田中 健太郎</p>
                <p className="text-xs text-gray-500 mb-2">中小企業診断士 / ファイナンシャルプランナー</p>
                <p className="text-sm text-gray-600 leading-relaxed">
                  大手銀行で15年間の融資業務経験を経て独立。中小企業の資金繰り改善を専門とし、ファクタリングを含む多様な資金調達手段のアドバイスを提供。延べ500社以上の資金繰り相談に対応。
                </p>
              </div>
            </div>
          </div>
          <p className="text-xs text-gray-400 mt-4 border-t border-gray-100 pt-4">
            ※ 当サイトのランキング・評価は、手数料、入金速度、口コミ評判、サービスの充実度等を独自の基準で総合的に評価しています。
          </p>
        </div>
      </section>

      {/* ==================== 8. CTA Banner ==================== */}
      <section className="bg-gradient-to-br from-primary-darker via-primary-dark to-primary py-16">
        <div className="max-w-3xl mx-auto px-4 text-center text-white">
          <div className="mb-6">
            <svg
              className="w-16 h-16 mx-auto opacity-80"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
              />
            </svg>
          </div>
          <h2 className="text-2xl md:text-3xl font-bold mb-4">
            どのファクタリング業者が最適か
            <br className="md:hidden" />
            分からない方へ
          </h2>
          <p className="text-blue-200 mb-8 max-w-lg mx-auto">
            30秒の簡単入力で、あなたの条件に合った業者を無料でご紹介します。
            まずはお気軽にお試しください。
          </p>
          <a
            href="/estimate"
            className="inline-block bg-cta hover:bg-cta-dark text-white px-10 py-4 rounded-xl text-lg font-bold transition-colors shadow-lg pulse-cta"
          >
            無料で一括見積もりする
          </a>
          <p className="text-sm text-blue-300 mt-4">
            ※ 完全無料・最短30秒で入力完了
          </p>
        </div>
      </section>
    </>
  );
}
