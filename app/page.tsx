import { prisma } from "@/lib/prisma";
import { CompanyCard } from "@/components/CompanyCard";
import Image from "next/image";

export const dynamic = "force-dynamic";

const medalColors = [
  { bg: "bg-amber-400", text: "text-amber-900", label: "No.1", border: "border-amber-400" },
  { bg: "bg-gray-300", text: "text-gray-700", label: "No.2", border: "border-gray-300" },
  { bg: "bg-orange-400", text: "text-orange-900", label: "No.3", border: "border-orange-400" },
];

const industries = [
  {
    name: "建設業",
    href: "/articles/construction-factoring",
    icon: "/images/icon-construction.jpg",
    desc: "工事代金の入金サイクルが長い建設業に最適",
  },
  {
    name: "運送業",
    href: "/articles/transport-factoring",
    icon: "/images/icon-transport.jpg",
    desc: "燃料費・車両維持費の資金繰りをサポート",
  },
  {
    name: "IT・フリーランス",
    href: "/articles/it-freelance-factoring",
    icon: "/images/icon-it.jpg",
    desc: "少額債権もOK、個人でも利用しやすい",
  },
  {
    name: "医療・介護",
    href: "/articles/medical-factoring",
    icon: "/images/icon-medical.jpg",
    desc: "診療報酬債権の早期現金化が可能",
  },
  {
    name: "個人事業主",
    href: "/articles/sole-proprietor-factoring",
    icon: "/images/icon-sole.jpg",
    desc: "法人でなくても利用できる業者を厳選",
  },
];

function AdvisorComment({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-3 items-start my-6 bg-primary/5 border border-primary/10 rounded-xl p-4">
      <div className="w-12 h-12 rounded-full overflow-hidden shrink-0 border-2 border-primary/20">
        <Image src="/images/advisor-sanada-main.png" alt="真田" width={48} height={48} className="object-cover" />
      </div>
      <div className="flex-1">
        <p className="text-xs font-bold text-primary mb-1">アドバイザー 真田</p>
        <div className="text-sm text-gray-700 leading-relaxed">{children}</div>
      </div>
    </div>
  );
}

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
      {/* JSON-LD Structured Data */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@graph": [
              {
                "@type": "WebSite",
                name: "ファクセル",
                url: "https://factoring-media.vercel.app",
                description: "ファクタリング業者の口コミ・評判を比較。手数料・入金速度・審査基準で徹底比較し、最適な業者が見つかります。",
                publisher: {
                  "@type": "Organization",
                  name: "ファクセル",
                },
              },
              {
                "@type": "FAQPage",
                mainEntity: [
                  {
                    "@type": "Question",
                    name: "ファクタリングとは何ですか？",
                    acceptedAnswer: {
                      "@type": "Answer",
                      text: "ファクタリングとは、企業が保有する売掛金（請求書）をファクタリング会社に売却して、支払期日前に現金化する資金調達方法です。融資と異なり借入ではないため、信用情報に影響しません。",
                    },
                  },
                  {
                    "@type": "Question",
                    name: "ファクタリングの手数料の相場はいくらですか？",
                    acceptedAnswer: {
                      "@type": "Answer",
                      text: "2社間ファクタリングの手数料相場は5%〜20%、3社間ファクタリングは1%〜10%程度です。業者や取引条件により異なります。",
                    },
                  },
                  {
                    "@type": "Question",
                    name: "ファクタリングの審査に落ちることはありますか？",
                    acceptedAnswer: {
                      "@type": "Answer",
                      text: "審査は主に売掛先（取引先）の信用力で判断されるため、自社が赤字でも利用可能な場合が多いです。ただし売掛先の信用力が低い場合は断られることがあります。",
                    },
                  },
                  {
                    "@type": "Question",
                    name: "即日入金は本当に可能ですか？",
                    acceptedAnswer: {
                      "@type": "Answer",
                      text: "はい、最短10分〜即日入金に対応した業者があります。ただし午前中の申込みや必要書類の事前準備が条件となる場合が多いです。",
                    },
                  },
                  {
                    "@type": "Question",
                    name: "個人事業主でもファクタリングを利用できますか？",
                    acceptedAnswer: {
                      "@type": "Answer",
                      text: "はい、個人事業主やフリーランスでも利用可能な業者があります。ペイトナーファクタリングやラボルなど、1万円から少額対応している業者もあります。",
                    },
                  },
                ],
              },
            ],
          }),
        }}
      />

      {/* ==================== 1. Hero Section ==================== */}
      <section className="bg-gradient-to-br from-primary-darker via-primary-dark to-primary text-white overflow-hidden relative">
        <div className="max-w-6xl mx-auto px-4 pt-12 md:pt-16 pb-0 flex flex-col md:flex-row items-end gap-0">
          {/* Left: text content */}
          <div className="flex-1 text-center md:text-left pb-12 md:pb-16">
            {/* Badge */}
            <div className="inline-flex items-center gap-2 bg-white/10 border border-white/20 backdrop-blur-sm px-4 py-2 rounded-full text-sm mb-5">
              <span className="w-2 h-2 bg-secondary rounded-full animate-pulse" />
              <span className="font-bold text-white">2026年</span>
              <span className="text-blue-200">最新ランキング公開中</span>
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
            <div className="flex gap-0 justify-center md:justify-start">
              <div className="text-center px-5 py-3.5 bg-white/10 rounded-l-xl border border-white/15">
                <p className="text-3xl font-black leading-none"><span className="text-secondary-light">10</span><span className="text-base font-bold text-white">社</span></p>
                <p className="text-[11px] text-blue-300 mt-1.5">掲載業者数</p>
              </div>
              <div className="text-center px-5 py-3.5 bg-white/10 border-y border-white/15">
                <p className="text-3xl font-black leading-none"><span className="text-secondary-light">96</span><span className="text-base font-bold text-white">%</span></p>
                <p className="text-[11px] text-blue-300 mt-1.5">利用満足度</p>
              </div>
              <div className="text-center px-5 py-3.5 bg-white/10 rounded-r-xl border border-white/15">
                <p className="text-3xl font-black leading-none"><span className="text-white">最短</span><span className="text-secondary-light">10</span><span className="text-base font-bold text-white">分</span></p>
                <p className="text-[11px] text-blue-300 mt-1.5">入金スピード</p>
              </div>
            </div>
          </div>

          {/* Right: teleoperator cutout - aligned to bottom */}
          <div className="hidden md:block flex-shrink-0 self-end -ml-24">
            <Image
              src="/images/hero-teleop.png"
              alt="ファクセル - 無料相談"
              width={420}
              height={560}
              className="object-contain object-bottom"
              priority
            />
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

      {/* ==================== 3. TOP3 Ranking ==================== */}
      <section className="max-w-6xl mx-auto px-4 py-16">
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-1.5 bg-primary/5 border border-primary/10 px-4 py-1.5 rounded-full mb-3">
            <div className="w-1.5 h-1.5 bg-primary rounded-full" />
            <span className="text-sm font-bold text-primary">厳選ランキング</span>
          </div>
          <h2 className="text-2xl md:text-3xl font-black text-gray-900 mb-2">
            おすすめファクタリング業者 TOP3
          </h2>
          <p className="text-sm text-gray-500">
            2026年最新版 — 口コミ・手数料・入金速度を総合評価
          </p>
          <div className="w-16 h-0.5 bg-primary mx-auto mt-4" />
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {topCompanies.map((company) => (
            <CompanyCard key={company.slug} {...company} />
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

      <hr className="section-divider" />

      {/* ==================== Quick Comparison Table ==================== */}
      <section className="max-w-4xl mx-auto px-4 -mt-8 relative z-10 mb-12">
        <div className="bg-white rounded-2xl shadow-lg border border-gray-100 overflow-hidden">
          <div className="relative">
            <div className="text-center py-5 bg-gray-50 border-b border-gray-200">
              <div className="inline-flex items-center gap-1.5 mb-2">
                <div className="w-1 h-5 bg-primary rounded-full" />
                <h2 className="text-lg font-black text-gray-900">ファクタリング業者一覧</h2>
              </div>
              <p className="text-xs text-gray-500">手数料・入金速度・評価を一目で比較</p>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="px-4 py-4 text-left font-medium text-gray-600">順位</th>
                  <th className="px-4 py-4 text-left font-medium text-gray-600">業者名</th>
                  <th className="px-4 py-4 text-center font-medium text-gray-600">手数料</th>
                  <th className="px-4 py-4 text-center font-medium text-gray-600">入金速度</th>
                  <th className="px-4 py-4 text-center font-medium text-gray-600">評価</th>
                  <th className="px-4 py-4 text-center font-medium text-gray-600">詳細</th>
                </tr>
              </thead>
              <tbody>
                {top5Companies.map((c, i) => (
                  <tr key={c.slug} className={`border-b border-gray-100 ${i === 0 ? "bg-amber-50/50" : ""}`}>
                    <td className="px-4 py-4">
                      {i < 3 ? (
                        <Image
                          src={`/images/rank-${i + 1}.png`}
                          alt={`第${i + 1}位`}
                          width={36}
                          height={36}
                        />
                      ) : (
                        <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-primary/10 text-primary text-xs font-bold">
                          {i + 1}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-4 font-bold text-primary-darker whitespace-nowrap">{c.name}</td>
                    <td className="px-4 py-4 text-center font-bold whitespace-nowrap">{c.fee || "-"}</td>
                    <td className="px-4 py-4 text-center whitespace-nowrap">{c.depositSpeed || "-"}</td>
                    <td className="px-4 py-4 text-center">
                      <span className="text-star font-bold">{c.rating?.toFixed(1) || "-"}</span>
                    </td>
                    <td className="px-4 py-4 text-center">
                      <a href={`/companies/${c.slug}`} className="inline-block bg-cta text-white text-xs px-4 py-2.5 rounded-lg font-bold hover:bg-cta-dark transition-colors whitespace-nowrap">
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

      {/* ==================== 4. What is Factoring ==================== */}
      <section className="bg-gray-50 py-16">
        <div className="max-w-6xl mx-auto px-4">
          <div className="w-12 h-0.5 bg-primary mx-auto mb-4" />
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

            {/* Flow diagram */}
            <div className="my-6">
              <Image
                src="/images/section-flow-diagram.jpg"
                alt="ファクタリングの仕組み - あなたの会社・ファクタリング業者・取引先の関係"
                width={960}
                height={540}
                className="w-full rounded-xl"
              />
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

          <div className="mt-8 space-y-6">
            <AdvisorComment>
              ファクタリングは「借金」ではなく「売掛金の売却」です。そのため信用情報に記録されず、銀行融資の審査にも影響しません。資金繰りに困った時の選択肢として、まず知っておくべきサービスです。
            </AdvisorComment>

            <h3 className="text-lg font-bold text-gray-900">2社間ファクタリングと3社間ファクタリングの違い</h3>
            <div className="grid md:grid-cols-2 gap-4">
              <div className="bg-white rounded-lg border border-gray-200 p-4">
                <h4 className="font-bold text-primary mb-2">2社間ファクタリング</h4>
                <ul className="text-sm text-gray-600 space-y-1.5">
                  <li>・あなたとファクタリング会社の2者間で契約</li>
                  <li>・取引先に知られずに利用可能</li>
                  <li>・手数料相場: 5%〜20%</li>
                  <li>・入金スピード: 最短即日</li>
                  <li>・スピード重視の方におすすめ</li>
                </ul>
              </div>
              <div className="bg-white rounded-lg border border-gray-200 p-4">
                <h4 className="font-bold text-primary mb-2">3社間ファクタリング</h4>
                <ul className="text-sm text-gray-600 space-y-1.5">
                  <li>・あなた・ファクタリング会社・取引先の3者間で契約</li>
                  <li>・取引先の承諾が必要</li>
                  <li>・手数料相場: 1%〜10%</li>
                  <li>・入金スピード: 数日〜1週間</li>
                  <li>・手数料を抑えたい方におすすめ</li>
                </ul>
              </div>
            </div>

            <AdvisorComment>
              初めてファクタリングを利用する方には、取引先にバレない「2社間ファクタリング」が人気です。ただし手数料は3社間より高めなので、取引先との関係性が良好な場合は3社間も検討してみてください。
            </AdvisorComment>

            <h3 className="text-lg font-bold text-gray-900">ファクタリングと銀行融資の違い</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="bg-gray-100">
                    <th className="px-4 py-2 text-left font-medium text-gray-600 border-b">比較項目</th>
                    <th className="px-4 py-2 text-center font-medium text-primary border-b">ファクタリング</th>
                    <th className="px-4 py-2 text-center font-medium text-gray-600 border-b">銀行融資</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-b"><td className="px-4 py-2 text-gray-700">資金化スピード</td><td className="px-4 py-2 text-center font-bold text-primary">最短即日</td><td className="px-4 py-2 text-center">2週間〜1ヶ月</td></tr>
                  <tr className="border-b bg-gray-50"><td className="px-4 py-2 text-gray-700">審査基準</td><td className="px-4 py-2 text-center font-bold text-primary">売掛先の信用力</td><td className="px-4 py-2 text-center">自社の業績</td></tr>
                  <tr className="border-b"><td className="px-4 py-2 text-gray-700">信用情報への影響</td><td className="px-4 py-2 text-center font-bold text-primary">なし</td><td className="px-4 py-2 text-center">あり</td></tr>
                  <tr className="border-b bg-gray-50"><td className="px-4 py-2 text-gray-700">担保・保証人</td><td className="px-4 py-2 text-center font-bold text-primary">不要</td><td className="px-4 py-2 text-center">必要な場合あり</td></tr>
                  <tr className="border-b"><td className="px-4 py-2 text-gray-700">赤字決算での利用</td><td className="px-4 py-2 text-center font-bold text-primary">可能</td><td className="px-4 py-2 text-center">困難</td></tr>
                  <tr><td className="px-4 py-2 text-gray-700">コスト</td><td className="px-4 py-2 text-center">手数料2%〜20%</td><td className="px-4 py-2 text-center font-bold">金利1%〜3%</td></tr>
                </tbody>
              </table>
            </div>

            <AdvisorComment>
              銀行融資の方がコストは安いですが、審査に2週間以上かかります。「来週の支払いに間に合わない」という急ぎの場合はファクタリング一択です。理想は銀行融資をメインにしつつ、緊急時のバックアップとしてファクタリングを使い分けることです。
            </AdvisorComment>
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

      <hr className="section-divider" />

      {/* ==================== 5. Pain Points ==================== */}
      <section className="py-16 bg-white">
        <div className="max-w-4xl mx-auto px-4">
          <div className="w-12 h-0.5 bg-primary mx-auto mb-4" />
          <h2 className="text-2xl md:text-3xl font-bold text-primary-dark mb-10 text-center">
            こんなお悩みありませんか?
          </h2>

          <div className="grid md:grid-cols-3 gap-5 mb-10">
            {/* Pain 1 */}
            <div className="bg-white rounded-xl overflow-hidden shadow-sm border border-gray-100">
              <div className="h-40 relative">
                <Image src="/images/worry-cashflow.jpg" alt="資金繰りの悩み" fill className="object-cover" />
              </div>
              <div className="p-5">
                <p className="text-gray-700 font-medium">
                  売掛金の入金が2ヶ月後で資金繰りが厳しい...
                </p>
              </div>
            </div>
            {/* Pain 2 */}
            <div className="bg-white rounded-xl overflow-hidden shadow-sm border border-gray-100">
              <div className="h-40 relative">
                <Image src="/images/worry-rejected.jpg" alt="融資審査の悩み" fill className="object-cover" />
              </div>
              <div className="p-5">
                <p className="text-gray-700 font-medium">
                  銀行融資の審査に落ちてしまった...
                </p>
              </div>
            </div>
            {/* Pain 3 */}
            <div className="bg-white rounded-xl overflow-hidden shadow-sm border border-gray-100">
              <div className="h-40 relative">
                <Image src="/images/worry-urgent.jpg" alt="急な出費の悩み" fill className="object-cover" />
              </div>
              <div className="p-5">
                <p className="text-gray-700 font-medium">
                  急な出費で今すぐ現金が必要...
                </p>
              </div>
            </div>
          </div>

          {/* Solution */}
          <div className="relative">
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

          <div className="max-w-3xl mx-auto mt-8 text-center">
            <AdvisorComment>
              多くの経営者が「ファクタリングは怪しい」と思っていますが、売掛債権の売買は民法で認められた合法的な取引です。ただし悪質な業者も存在するため、当サイトでは厳選した優良業者のみをご紹介しています。
            </AdvisorComment>
          </div>
        </div>
      </section>

      {/* ==================== 6. Industry Recommendations ==================== */}
      <section className="bg-gray-50 py-16">
        <div className="max-w-6xl mx-auto px-4">
          <div className="w-12 h-0.5 bg-primary mx-auto mb-4" />
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
                <div className="w-14 h-14 mx-auto mb-3">
                  <Image src={industry.icon} alt={industry.name} width={64} height={64} className="rounded-full" />
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

      <hr className="section-divider" />

      {/* ==================== FAQ Section ==================== */}
      <section className="bg-white py-16">
        <div className="max-w-4xl mx-auto px-4">
          <div className="w-12 h-0.5 bg-primary mx-auto mb-4" />
          <h2 className="text-2xl font-bold text-gray-900 mb-8 text-center">
            よくある質問
          </h2>
          <div className="space-y-4">
            {[
              {
                q: "ファクタリングとは何ですか？",
                a: "ファクタリングとは、企業が保有する売掛金（請求書）をファクタリング会社に売却して、支払期日前に現金化する資金調達方法です。銀行融資とは異なり「借入」ではないため、貸借対照表の負債が増えず、信用情報にも影響しません。最短即日で資金を得ることができ、赤字決算や税金滞納があっても利用可能な場合が多いのが特徴です。",
              },
              {
                q: "ファクタリングの手数料の相場はいくらですか？",
                a: "2社間ファクタリング（取引先に知らせない方式）の手数料相場は5%〜20%、3社間ファクタリング（取引先の承諾が必要な方式）は1%〜10%程度です。手数料は売掛先の信用力、売掛金の金額、支払期日までの日数などにより変動します。OLTAは2%〜9%、ペイトナーファクタリングは一律10%と明確な料金体系を提示しています。",
              },
              {
                q: "ファクタリングの審査に落ちることはありますか？",
                a: "ファクタリングの審査は主に売掛先（取引先）の信用力で判断されるため、自社が赤字や債務超過でも利用可能な場合が多いです。審査通過率93%以上を公表している業者もあります。ただし、売掛先が個人や設立間もない企業の場合、また売掛金の存在が確認できない場合は断られることがあります。",
              },
              {
                q: "即日入金は本当に可能ですか？",
                a: "はい、最短10分（ペイトナーファクタリング）から即日入金に対応した業者が複数あります。ただし、即日入金を確実にするためには、午前中の申込み、必要書類（本人確認書類・請求書・通帳コピーなど）の事前準備、オンライン完結型業者の利用が条件となる場合が多いです。",
              },
              {
                q: "個人事業主でもファクタリングを利用できますか？",
                a: "はい、個人事業主やフリーランスでも利用可能な業者が増えています。ペイトナーファクタリングやラボルは1万円から少額対応しており、請求書1枚から利用できます。法人向けの大手業者でも個人事業主に対応しているケースが多くあります。",
              },
              {
                q: "取引先にファクタリングの利用がバレますか？",
                a: "2社間ファクタリングであれば、取引先に知られることなく利用できます。契約はあなたとファクタリング会社の2者間で行われるため、取引先への通知は不要です。一方、3社間ファクタリングは取引先の承諾が必要ですが、手数料が低いメリットがあります。",
              },
            ].map((item, i) => (
              <details key={i} className="group border border-gray-200 rounded-lg">
                <summary className="flex items-center justify-between px-5 py-4 cursor-pointer hover:bg-gray-50 transition-colors">
                  <span className="font-bold text-gray-800 text-sm pr-4">{item.q}</span>
                  <svg className="w-5 h-5 text-gray-400 shrink-0 group-open:rotate-180 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </summary>
                <div className="px-5 pb-4">
                  <p className="text-sm text-gray-600 leading-relaxed">{item.a}</p>
                </div>
              </details>
            ))}
          </div>

          <AdvisorComment>
            ファクタリングは正しく使えば非常に有効な資金調達手段です。特に「売上はあるのにキャッシュがない」という状況の企業にとっては、最も合理的な選択肢と言えます。まずは複数社から見積もりを取って、手数料と条件を比較することをおすすめします。
          </AdvisorComment>
        </div>
      </section>

      <hr className="section-divider" />

      {/* ==================== How to Use Section ==================== */}
      <section className="py-16">
        <div className="max-w-4xl mx-auto px-4">
          <div className="w-12 h-0.5 bg-primary mx-auto mb-4" />
          <h2 className="text-2xl font-bold text-gray-900 mb-8 text-center">
            ファクタリング利用の流れ
          </h2>
          <div className="space-y-0">
            {[
              { step: "1", title: "無料相談・見積もり依頼", desc: "当サイトの一括見積もりフォームから、事業形態・請求書金額・急ぎ度を入力するだけ。最短30秒で複数社に見積もり依頼ができます。" },
              { step: "2", title: "業者から連絡・条件提示", desc: "入力内容に基づいて、最適なファクタリング業者から手数料・入金スピードなどの条件が提示されます。複数社の条件を比較検討できます。" },
              { step: "3", title: "必要書類の提出", desc: "本人確認書類、請求書、通帳のコピーなど、必要書類を提出します。オンライン完結型の業者なら、スマホで写真を撮って送るだけで完了します。" },
              { step: "4", title: "審査・契約", desc: "売掛先の信用力をもとに審査が行われます。最短10分〜数時間で審査完了。条件に合意すれば電子契約で締結します。" },
              { step: "5", title: "入金", desc: "契約完了後、最短即日で指定の銀行口座に入金されます。あとは支払期日に売掛先から入金があれば、ファクタリング会社に支払いを行います。" },
            ].map((item, i) => (
              <div key={i} className="flex gap-4">
                <div className="flex flex-col items-center">
                  <div className="w-10 h-10 bg-primary text-white rounded-full flex items-center justify-center font-bold text-sm shrink-0">
                    {item.step}
                  </div>
                  {i < 4 && <div className="w-0.5 h-full bg-primary/20 my-1" />}
                </div>
                <div className="pb-8">
                  <h3 className="font-bold text-gray-900 mb-1">{item.title}</h3>
                  <p className="text-sm text-gray-600 leading-relaxed">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <hr className="section-divider" />

      {/* ==================== Selection Points Section ==================== */}
      <section className="bg-white py-16">
        <div className="max-w-4xl mx-auto px-4">
          <div className="w-12 h-0.5 bg-primary mx-auto mb-4" />
          <h2 className="text-2xl font-bold text-gray-900 mb-8 text-center">
            ファクタリング業者を選ぶ5つのポイント
          </h2>
          <div className="space-y-6">
            {[
              { num: "1", title: "手数料の透明性", desc: "手数料の範囲が明確に提示されているかを確認しましょう。「1%〜」のように下限だけを強調し、実際には高い手数料を請求する業者も存在します。OLTAの2%〜9%やペイトナーの一律10%のように、上限も明示している業者が信頼できます。" },
              { num: "2", title: "入金スピードと対応時間", desc: "即日入金を謳っていても、「午前中の申込みに限る」「初回は翌営業日」などの条件がある場合があります。24時間対応のえんナビや、土日も審査可能な業者を選ぶと急ぎの資金需要にも対応できます。" },
              { num: "3", title: "運営会社の信頼性", desc: "会社の所在地・設立年数・資本金・代表者名が明記されているか確認しましょう。日本中小企業金融サポート機構のような一般社団法人や、上場企業グループのラボル（東証プライム上場・セレス子会社）は特に信頼性が高いです。" },
              { num: "4", title: "契約条件（償還請求権の有無）", desc: "ノンリコース（償還請求権なし）の契約であれば、万が一売掛先が倒産しても返金義務がありません。リコース契約の場合は実質的に借入と変わらないため、契約前に必ず確認しましょう。" },
              { num: "5", title: "実際の利用者の口コミ", desc: "公式サイトの情報だけでなく、実際に利用した方の口コミ・評判を確認することが重要です。当サイトでは各業者の口コミを掲載していますので、業者選びの参考にしてください。" },
            ].map((item) => (
              <div key={item.num} className="flex gap-4">
                <div className="w-8 h-8 bg-primary/10 text-primary rounded-full flex items-center justify-center font-bold text-sm shrink-0 mt-0.5">
                  {item.num}
                </div>
                <div>
                  <h3 className="font-bold text-gray-900 mb-1">{item.title}</h3>
                  <p className="text-sm text-gray-600 leading-relaxed">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
          <AdvisorComment>
            業者選びで最も重要なのは「手数料の透明性」と「契約条件の確認」です。見積もり段階で手数料の上限を明示しない業者や、契約書の内容を十分に説明しない業者は避けましょう。当サイトに掲載している業者は、いずれも手数料体系が明確な優良企業です。
          </AdvisorComment>

          <div className="text-center mt-8">
            <a href="/articles/how-to-choose" className="text-primary font-bold text-sm hover:underline">
              業者の選び方をもっと詳しく見る →
            </a>
          </div>
        </div>
      </section>

      <hr className="section-divider" />

      {/* ==================== Case Studies Section ==================== */}
      <section className="bg-gray-50 py-16">
        <div className="max-w-6xl mx-auto px-4">
          <div className="text-center mb-10">
            <div className="w-12 h-0.5 bg-primary mx-auto mb-4" />
            <h2 className="text-2xl md:text-3xl font-bold text-primary-darker mb-3">
              ファクタリング活用事例
            </h2>
            <p className="text-gray-500">
              実際にファクタリングで資金繰りを改善した事例をご紹介
            </p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[
              {
                image: "/images/case-construction.jpg",
                industry: "建設業",
                title: "工事代金の入金を3ヶ月→即日に短縮",
                amount: "500万円",
                fee: "4.5%",
                speed: "即日",
                body: "大型工事の下請けで、元請からの入金が3ヶ月後。材料費の支払いが先行し資金繰りが悪化していたが、ファクタリングで売掛金を即日現金化。追加の工事案件も受注できるようになった。",
              },
              {
                image: "/images/case-transport.jpg",
                industry: "運送業",
                title: "燃料費高騰でも安定した経営を実現",
                amount: "300万円",
                fee: "5.0%",
                speed: "翌日",
                body: "燃料費が前年比30%上昇し、月末の支払いが厳しくなっていた。売掛金をファクタリングで早期現金化し、燃料費の支払いに充当。ドライバーの給与遅延もなくなった。",
              },
              {
                image: "/images/case-freelance.jpg",
                industry: "ITフリーランス",
                title: "請求書1枚・10万円から即日入金",
                amount: "45万円",
                fee: "10%",
                speed: "最短10分",
                body: "大手SIerの案件で月末締め翌々月払い。生活費が足りなくなりペイトナーファクタリングを利用。請求書をアップロードするだけで10分後に入金され、非常に助かった。",
              },
              {
                image: "/images/case-medical.jpg",
                industry: "医療（クリニック）",
                title: "診療報酬の入金待ち2ヶ月を解消",
                amount: "800万円",
                fee: "1.5%",
                speed: "3営業日",
                body: "開業2年目のクリニック。診療報酬の入金が2ヶ月後で、医療機器のリース料や人件費の支払いに苦労。診療報酬ファクタリングで手数料わずか1.5%で資金化できた。",
              },
              {
                image: "/images/case-cafe.jpg",
                industry: "飲食（カフェ経営）",
                title: "コロナ後の売上回復期に資金確保",
                amount: "80万円",
                fee: "8.0%",
                speed: "即日",
                body: "法人向けケータリングの売掛金があったが、仕入れ費用が先に必要だった。ファクタリングで即日80万円を調達し、食材の仕入れと新メニュー開発に充てることができた。",
              },
            ].map((c, i) => (
              <div key={i} className="bg-white rounded-xl overflow-hidden shadow-sm card-hover border border-gray-100">
                <div className="relative h-48">
                  <Image
                    src={c.image}
                    alt={`${c.industry}のファクタリング活用事例`}
                    fill
                    className="object-cover"
                  />
                  <div className="absolute top-3 left-3">
                    <span className="bg-primary text-white text-xs font-bold px-3 py-1 rounded-full">
                      {c.industry}
                    </span>
                  </div>
                </div>
                <div className="p-5">
                  <h3 className="font-bold text-primary-darker mb-2">{c.title}</h3>
                  <div className="flex gap-3 mb-3">
                    <div className="bg-primary/5 rounded-lg px-2.5 py-1.5 text-center flex-1">
                      <span className="text-[10px] text-gray-400 block">調達額</span>
                      <span className="text-sm font-bold text-primary">{c.amount}</span>
                    </div>
                    <div className="bg-secondary/5 rounded-lg px-2.5 py-1.5 text-center flex-1">
                      <span className="text-[10px] text-gray-400 block">手数料</span>
                      <span className="text-sm font-bold text-secondary">{c.fee}</span>
                    </div>
                    <div className="bg-green/5 rounded-lg px-2.5 py-1.5 text-center flex-1">
                      <span className="text-[10px] text-gray-400 block">入金</span>
                      <span className="text-sm font-bold text-green">{c.speed}</span>
                    </div>
                  </div>
                  <p className="text-sm text-gray-600 leading-relaxed">{c.body}</p>
                </div>
              </div>
            ))}
          </div>
          <AdvisorComment>
            上記はあくまで一例ですが、ファクタリングは業種を問わず活用できます。「うちの業種でも使えるの？」と不安な方は、まず無料の一括見積もりをお試しください。対応可能かどうかも含めて、各業者から回答が届きます。
          </AdvisorComment>

          <div className="text-center mt-8">
            <a
              href="/estimate"
              className="inline-block bg-cta hover:bg-cta-dark text-white px-8 py-4 rounded-xl font-bold transition-colors shadow-md pulse-cta"
            >
              あなたも無料で見積もりしてみる
            </a>
          </div>
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
