import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

async function main() {
  const companies = [
    {
      slug: "ququmo",
      name: "QuQuMo（ククモ）",
      officialUrl: "https://ququmo.com/",
      description:
        "最短2時間で入金可能なオンラインファクタリング。手数料1%〜14.8%で、買取金額に上限なし。法人・個人事業主対応。",
      minAmount: 1,
      maxAmount: null,
      fee: "1%〜14.8%",
      depositSpeed: "最短2時間",
      targetBusiness: "法人・個人事業主",
      features: [
        "最短2時間入金",
        "買取上限なし",
        "オンライン完結",
        "手数料1%〜",
      ],
      pros: [
        "入金スピードが非常に速い",
        "買取金額の上限がない",
        "手数料の下限が1%と業界最安級",
        "必要書類が少ない",
      ],
      cons: [
        "手数料の幅が広い（最大14.8%）",
        "実績がOLTAほど多くない",
      ],
      rating: 4.5,
      isRecommended: true,
      rankingOrder: 1,
    },
    {
      slug: "beat-trading",
      name: "ビートレーディング",
      officialUrl: "https://betrading.jp/",
      description:
        "累計買取額1,300億円超の実績を持つ老舗ファクタリング会社。2社間・3社間両対応で、最短5時間で入金。対面・オンライン両方可能。",
      minAmount: null,
      maxAmount: null,
      fee: "2%〜12%",
      depositSpeed: "最短5時間",
      targetBusiness: "法人・個人事業主",
      features: [
        "累計1,300億円超の実績",
        "2社間・3社間対応",
        "対面可能",
        "大口対応",
      ],
      pros: [
        "業界トップクラスの実績と信頼性",
        "大口案件にも対応可能",
        "2社間・3社間の両方に対応",
        "担当者の対応が丁寧",
      ],
      cons: [
        "手数料がやや高め",
        "オンライン完結ではない場合がある",
        "即日入金は時間帯による",
      ],
      rating: 4.4,
      isRecommended: true,
      rankingOrder: 2,
    },
    {
      slug: "factoru",
      name: "ファクトル",
      officialUrl: "https://factoru.chushokigyo-support.or.jp/",
      description:
        "一般社団法人日本中小企業金融サポート機構が運営するオンラインファクタリング。AI審査で最短即日入金。非営利法人の信頼性とオンラインの手軽さを両立。",
      minAmount: null,
      maxAmount: null,
      fee: "1.5%〜10%",
      depositSpeed: "最短即日",
      targetBusiness: "法人・個人事業主",
      features: [
        "非営利法人運営",
        "AI審査",
        "オンライン完結",
        "認定経営革新等支援機関",
      ],
      pros: [
        "一般社団法人運営で信頼性が非常に高い",
        "AI審査で迅速な対応",
        "手数料が良心的（1.5%〜10%）",
        "経営相談にも対応可能",
      ],
      cons: [
        "サービス開始が比較的新しい",
        "知名度がまだ高くない",
      ],
      rating: 4.3,
      isRecommended: true,
      rankingOrder: 3,
    },
    {
      slug: "jfc-support",
      name: "日本中小企業金融サポート機構",
      officialUrl: "https://chushokigyo-support.or.jp/",
      description:
        "一般社団法人が運営する非営利のファクタリング。手数料1.5%〜10%と良心的。関東財務局長の認定経営革新等支援機関。対面での丁寧なサポートが特徴。",
      minAmount: null,
      maxAmount: null,
      fee: "1.5%〜10%",
      depositSpeed: "最短即日",
      targetBusiness: "法人・個人事業主",
      features: [
        "非営利法人運営",
        "認定経営革新等支援機関",
        "良心的な手数料",
        "経営相談可能",
      ],
      pros: [
        "非営利法人で信頼性が高い",
        "手数料が良心的",
        "経営相談にも対応",
        "国の認定機関である安心感",
      ],
      cons: [
        "審査に時間がかかることがある",
        "スピード面では専門業者に劣る",
        "対面が基本",
      ],
      rating: 4.1,
      isRecommended: false,
      rankingOrder: 4,
    },
    {
      slug: "accel-factor",
      name: "アクセルファクター",
      officialUrl: "https://accelfacter.co.jp/",
      description:
        "最短即日入金のスピード対応が強み。少額30万円から利用可能で、中小企業・個人事業主に幅広く対応。審査通過率93%以上。",
      minAmount: 30,
      maxAmount: 10000,
      fee: "2%〜20%",
      depositSpeed: "最短即日",
      targetBusiness: "法人・個人事業主",
      features: [
        "審査通過率93%以上",
        "少額30万円〜",
        "即日入金",
        "柔軟な審査",
      ],
      pros: [
        "審査通過率が高い",
        "少額から利用可能",
        "柔軟な審査基準",
        "スタッフの対応が丁寧",
      ],
      cons: [
        "手数料の上限がやや高い",
        "対面が必要な場合がある",
      ],
      rating: 4.0,
      isRecommended: false,
      rankingOrder: 5,
    },
    {
      slug: "olta",
      name: "OLTA（オルタ）",
      officialUrl: "https://www.olta.co.jp/",
      description:
        "AI審査による最短即日のクラウドファクタリング。2社間ファクタリング専門で、手数料は業界最低水準の2%〜9%。オンライン完結で面談不要。",
      minAmount: 1,
      maxAmount: null,
      fee: "2%〜9%",
      depositSpeed: "最短即日",
      targetBusiness: "法人・個人事業主",
      features: [
        "手数料2%〜9%で業界最安級",
        "AI審査",
        "面談不要",
        "2社間専門",
        "オンライン完結",
      ],
      pros: [
        "業界最低水準の手数料",
        "AI審査で最短即日入金",
        "オンラインで完結、来店不要",
        "債権譲渡登記不要",
      ],
      cons: [
        "3社間ファクタリングには非対応",
        "初回利用は審査に時間がかかる場合あり",
      ],
      rating: 4.5,
      isRecommended: false,
      rankingOrder: 6,
    },
    {
      slug: "pmg",
      name: "PMG（ピーエムジー）",
      officialUrl: "https://p-m-g.tokyo/",
      description:
        "新会社設立から対応可能なファクタリング。最短即日入金で、5,000万円までの大口にも対応。個別の丁寧なサポートが特徴。",
      minAmount: 50,
      maxAmount: 5000,
      fee: "2%〜15%",
      depositSpeed: "最短即日",
      targetBusiness: "法人",
      features: [
        "大口5,000万円まで対応",
        "新規設立法人OK",
        "丁寧なサポート",
        "即日入金",
      ],
      pros: [
        "大口案件に強い",
        "設立間もない会社でも利用可能",
        "専任担当者制で安心",
        "リピート利用で手数料優遇",
      ],
      cons: [
        "個人事業主は利用不可",
        "少額利用には向かない",
        "東京近郊がメイン",
      ],
      rating: 3.9,
      isRecommended: false,
      rankingOrder: 7,
    },
    {
      slug: "paytoday",
      name: "ペイトナーファクタリング",
      officialUrl: "https://paytner.co.jp/factoring",
      description:
        "フリーランス・個人事業主に特化したファクタリングサービス。最短10分で審査完了、即日入金。請求書1枚から利用可能。",
      minAmount: 1,
      maxAmount: 100,
      fee: "一律10%",
      depositSpeed: "最短10分",
      targetBusiness: "フリーランス・個人事業主",
      features: [
        "最短10分審査",
        "フリーランス特化",
        "請求書1枚からOK",
        "オンライン完結",
      ],
      pros: [
        "審査スピードが圧倒的に速い",
        "少額から利用可能",
        "手数料が明確（一律10%）",
        "初めての方でも使いやすい",
      ],
      cons: [
        "買取上限が100万円まで",
        "法人の大口利用には不向き",
        "手数料がやや高め",
      ],
      rating: 4.3,
      isRecommended: false,
      rankingOrder: 8,
    },
    {
      slug: "labol",
      name: "ラボル",
      officialUrl: "https://labol.co.jp/",
      description:
        "フリーランス向け即日払いサービス。最短60分で入金、1万円から利用可能。手数料は一律10%でシンプル。東証プライム上場企業のグループ会社。",
      minAmount: 1,
      maxAmount: null,
      fee: "一律10%",
      depositSpeed: "最短60分",
      targetBusiness: "フリーランス・個人事業主",
      features: [
        "最短60分入金",
        "1万円から利用可",
        "上場企業グループ",
        "手数料一律10%",
      ],
      pros: [
        "上場企業グループの信頼性",
        "1万円から少額利用可能",
        "手数料が明確でわかりやすい",
        "24時間365日振込対応",
      ],
      cons: [
        "手数料がやや高い（一律10%）",
        "法人は利用不可",
        "買取上限が低め",
      ],
      rating: 4.0,
      isRecommended: false,
      rankingOrder: 9,
    },
    {
      slug: "top-management",
      name: "トップマネジメント",
      officialUrl: "https://top-management.co.jp/",
      description:
        "業界歴15年以上の老舗ファクタリング会社。2社間・3社間対応で、最短即日入金。1億円までの大口案件にも対応可能。",
      minAmount: 30,
      maxAmount: 10000,
      fee: "1%〜15%",
      depositSpeed: "最短即日",
      targetBusiness: "法人・個人事業主",
      features: [
        "業界歴15年以上",
        "大口1億円まで対応",
        "2社間・3社間対応",
        "ゼロファク（補助金連動型）",
      ],
      pros: [
        "長年の実績があり信頼性が高い",
        "独自のゼロファクサービスがある",
        "大口案件に対応",
        "丁寧なコンサルティング",
      ],
      cons: [
        "手数料の幅が広い",
        "審査に時間がかかることがある",
        "オンライン完結ではない場合あり",
      ],
      rating: 3.8,
      isRecommended: false,
      rankingOrder: 10,
    },
  ];

  // Delete removed company
  await prisma.company.deleteMany({
    where: { slug: "ennavi" },
  });

  for (const company of companies) {
    await prisma.company.upsert({
      where: { slug: company.slug },
      update: company,
      create: company,
    });
  }

  console.log("Seed data inserted successfully: 10 companies");
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
