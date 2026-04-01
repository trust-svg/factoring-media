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

  // Insert sample reviews
  const reviews = [
    // QuQuMo (1位)
    { companySlug: "ququmo", rating: 5, title: "最短2時間で本当に入金された", body: "月末の支払いに間に合わないと焦っていた時に利用しました。午前中に申し込んで、昼過ぎには入金されていました。手数料は5%程度で、思ったより安かったです。オンラインで完結するので、忙しい時でも助かりました。", userType: "法人（小規模）", isApproved: true },
    { companySlug: "ququmo", rating: 4, title: "手数料の幅が広いのが少し不安だった", body: "手数料1%〜14.8%と幅があるので、実際にいくらになるか不安でしたが、見積もりの段階で明確に提示してもらえました。結果的に7%で利用でき、満足しています。次回も利用したいと思います。", userType: "個人事業主", isApproved: true },
    { companySlug: "ququmo", rating: 5, title: "買取上限がないのが決め手", body: "800万円の売掛金を買い取ってもらいました。他社では上限がある場合が多いですが、QuQuMoは上限なしなので大口案件でも安心です。担当者の対応も丁寧で、信頼できる業者だと感じました。", userType: "法人（中規模）", isApproved: true },
    { companySlug: "ququmo", rating: 4, title: "2回目以降は手数料が下がった", body: "初回は8%でしたが、2回目の利用時は6%に下がりました。リピーター優遇があるようで、継続的に利用するならメリットが大きいと思います。", userType: "法人（小規模）", isApproved: true },

    // ビートレーディング (2位)
    { companySlug: "beat-trading", rating: 5, title: "実績があるので安心して利用できた", body: "累計1,300億円の実績がある老舗だったので、初めてのファクタリングでも安心でした。担当者が仕組みを丁寧に説明してくれて、不安が解消されました。入金も翌日には完了し、助かりました。", userType: "法人（小規模）", isApproved: true },
    { companySlug: "beat-trading", rating: 4, title: "3社間で手数料を抑えられた", body: "取引先に相談したところ快諾してもらえたので、3社間ファクタリングを利用しました。手数料は3%で済み、非常にコストパフォーマンスが良かったです。2社間と3社間の両方に対応しているのは強みだと思います。", userType: "法人（中規模）", isApproved: true },
    { companySlug: "beat-trading", rating: 4, title: "対面での相談ができて安心", body: "オンライン完結型が多い中、対面で相談できるのは安心感がありました。東京オフィスに行って、直接話を聞けたのが良かったです。ただ、地方の場合はオンラインになるので、その点は注意が必要です。", userType: "個人事業主", isApproved: true },
    { companySlug: "beat-trading", rating: 5, title: "大口案件もスムーズに対応", body: "2,000万円の大口案件でしたが、スムーズに対応してもらえました。審査も迅速で、3営業日で入金完了。大口に強いという評判は本当でした。", userType: "法人（中規模）", isApproved: true },

    // ファクトル (3位)
    { companySlug: "factoru", rating: 5, title: "非営利法人が運営しているので安心", body: "一般社団法人が運営しているという点で、信頼性が高いと感じました。手数料も4%と良心的で、初めてのファクタリングでも安心して利用できました。AI審査でスピーディーなのも良かったです。", userType: "法人（小規模）", isApproved: true },
    { companySlug: "factoru", rating: 4, title: "オンライン完結で手軽", body: "以前は母体の日本中小企業金融サポート機構に対面で相談していましたが、ファクトルはオンラインで完結するので便利です。手数料も変わらず良心的で、使い勝手が良くなりました。", userType: "個人事業主", isApproved: true },
    { companySlug: "factoru", rating: 5, title: "経営相談もできるのが嬉しい", body: "ファクタリングだけでなく、資金繰り全般の相談にも乗ってもらえました。認定経営革新等支援機関なので、補助金の情報なども教えてもらえて、非常に有益でした。", userType: "法人（小規模）", isApproved: true },

    // 日本中小企業金融サポート機構 (4位)
    { companySlug: "jfc-support", rating: 5, title: "国の認定機関なので信頼できる", body: "関東財務局長の認定を受けている機関なので、安心して相談できました。手数料は2%で済み、非常に良心的。営利目的ではないので、本当に利用者のことを考えてくれている印象を受けました。", userType: "法人（小規模）", isApproved: true },
    { companySlug: "jfc-support", rating: 4, title: "対応は丁寧だが時間がかかる", body: "担当者の対応は非常に丁寧で信頼感がありましたが、審査に3日ほどかかりました。即日入金が必要な場合は不向きですが、時間に余裕がある場合はおすすめです。手数料の安さは業界トップクラスです。", userType: "個人事業主", isApproved: true },
    { companySlug: "jfc-support", rating: 4, title: "補助金の相談もできた", body: "ファクタリングの相談をしたついでに、事業再構築補助金の情報も教えてもらえました。経営全般のサポートをしてもらえるのは、他のファクタリング会社にはないメリットだと思います。", userType: "法人（中規模）", isApproved: true },

    // アクセルファクター (5位)
    { companySlug: "accel-factor", rating: 5, title: "他社で断られたが審査に通った", body: "売掛先が小さい会社だったため、他社では断られてしまいましたが、アクセルファクターでは審査に通りました。通過率93%というのは本当のようです。手数料は12%とやや高めでしたが、資金繰りが助かったので満足しています。", userType: "個人事業主", isApproved: true },
    { companySlug: "accel-factor", rating: 4, title: "少額30万円でも対応してくれた", body: "30万円の少額でも嫌な顔ひとつせず対応してくれました。少額だと断る業者も多い中、ありがたかったです。手数料は15%でしたが、少額なのでこのくらいかなと思います。", userType: "フリーランス", isApproved: true },
    { companySlug: "accel-factor", rating: 4, title: "スタッフの対応が親切", body: "初めてのファクタリングで不安でしたが、スタッフが丁寧に説明してくれたので安心できました。即日入金も実現し、月末の支払いに間に合いました。", userType: "法人（小規模）", isApproved: true },

    // OLTA (6位)
    { companySlug: "olta", rating: 5, title: "手数料の安さが圧倒的", body: "複数社に見積もりを取りましたが、OLTAが最も手数料が安かったです。3%で利用でき、銀行融資の金利と比べてもそこまで変わらない水準でした。AI審査で即日入金も実現し、非常に満足しています。", userType: "法人（小規模）", isApproved: true },
    { companySlug: "olta", rating: 5, title: "オンラインで全て完結した", body: "地方在住なので来店不要のオンライン完結型を探していました。OLTAは申込みから入金まで全てWebで完結し、非常にスムーズでした。必要書類も少なく、手間がかかりません。", userType: "個人事業主", isApproved: true },
    { companySlug: "olta", rating: 4, title: "初回は審査に少し時間がかかった", body: "初回利用時は審査に半日ほどかかりました。即日入金を期待していたので少し焦りましたが、翌朝には入金されていました。2回目以降は本当に即日で処理されるようになりました。", userType: "法人（小規模）", isApproved: true },

    // PMG (7位)
    { companySlug: "pmg", rating: 4, title: "大口案件に対応してもらえた", body: "3,000万円の大口案件でしたが、問題なく対応してもらえました。専任の担当者がついてくれて、細かい質問にも丁寧に答えてもらえました。法人向けのサービスとしては非常に質が高いと感じました。", userType: "法人（中規模）", isApproved: true },
    { companySlug: "pmg", rating: 4, title: "設立1年目でも利用できた", body: "設立して間もない会社でしたが、利用できました。銀行融資はまだ難しい段階だったので、ファクタリングという選択肢があって本当に助かりました。", userType: "法人（小規模）", isApproved: true },
    { companySlug: "pmg", rating: 3, title: "個人事業主は利用不可", body: "問い合わせたところ、個人事業主は対象外と言われました。法人限定なので、その点は事前に確認が必要です。対応自体は丁寧でした。", userType: "個人事業主", isApproved: true },

    // ペイトナー (8位)
    { companySlug: "paytoday", rating: 5, title: "10分で審査完了は本当だった", body: "半信半疑で申し込みましたが、本当に10分で審査が完了し、すぐに入金されました。フリーランスとして月末の生活費が厳しい時に助かりました。手数料10%は安くはないですが、このスピード感は価値があります。", userType: "フリーランス", isApproved: true },
    { companySlug: "paytoday", rating: 4, title: "請求書1枚から使える手軽さ", body: "15万円の請求書1枚でも利用できました。他の業者は最低金額が高いところが多いですが、ペイトナーは少額でもOKなのがフリーランスには嬉しいです。", userType: "フリーランス", isApproved: true },
    { companySlug: "paytoday", rating: 3, title: "上限100万円は物足りない", body: "事業が成長してきて、100万円以上の請求書もファクタリングしたくなりましたが、上限が100万円なので使えません。少額向けと割り切って利用しています。", userType: "個人事業主", isApproved: true },

    // ラボル (9位)
    { companySlug: "labol", rating: 5, title: "1万円から使えるのが助かる", body: "駆け出しのフリーランスなので、請求額が小さいことが多いです。1万円から利用できるラボルは本当に助かっています。上場企業グループという安心感もあります。", userType: "フリーランス", isApproved: true },
    { companySlug: "labol", rating: 4, title: "24時間振込対応が便利", body: "金曜の夜に申し込んで、土曜の朝には入金されていました。24時間365日対応なので、急ぎの時にも安心です。手数料10%は少し高いですが、この利便性なら納得です。", userType: "フリーランス", isApproved: true },
    { companySlug: "labol", rating: 4, title: "セレスグループの安心感", body: "東証プライム上場のセレスのグループ会社なので、怪しい業者ではないという安心感があります。フリーランス向けのサービスは信頼性が重要なので、この点は大きなメリットです。", userType: "個人事業主", isApproved: true },

    // トップマネジメント (10位)
    { companySlug: "top-management", rating: 4, title: "業界歴15年の安心感", body: "15年以上の実績がある業者なので安心できました。大口の1億円案件にも対応可能とのことで、今後事業が拡大しても継続して利用できそうです。", userType: "法人（中規模）", isApproved: true },
    { companySlug: "top-management", rating: 4, title: "ゼロファクが面白い", body: "補助金と連動した「ゼロファク」というサービスがあり、実質的に手数料を抑えられる仕組みが面白いと感じました。他社にはないユニークなサービスです。", userType: "法人（小規模）", isApproved: true },
    { companySlug: "top-management", rating: 3, title: "審査に少し時間がかかった", body: "審査に2日ほどかかりました。即日を期待していたので少し残念でしたが、手数料は4%と安かったので結果的には満足しています。丁寧に審査している証拠かもしれません。", userType: "個人事業主", isApproved: true },
  ];

  for (const review of reviews) {
    const company = await prisma.company.findUnique({
      where: { slug: review.companySlug },
    });
    if (!company) continue;

    await prisma.review.create({
      data: {
        companyId: company.id,
        rating: review.rating,
        title: review.title,
        body: review.body,
        userType: review.userType,
        isApproved: review.isApproved,
      },
    });
  }

  // Update review counts and ratings
  const allCompanies = await prisma.company.findMany();
  for (const company of allCompanies) {
    const count = await prisma.review.count({
      where: { companyId: company.id, isApproved: true },
    });
    const avg = await prisma.review.aggregate({
      where: { companyId: company.id, isApproved: true },
      _avg: { rating: true },
    });
    await prisma.company.update({
      where: { id: company.id },
      data: {
        reviewCount: count,
        rating: avg._avg.rating ? Math.round(avg._avg.rating * 10) / 10 : company.rating,
      },
    });
  }

  console.log(`Reviews inserted: ${reviews.length}`);

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
