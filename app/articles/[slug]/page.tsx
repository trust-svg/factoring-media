import { ArticleLayout } from "@/components/ArticleLayout";
import { notFound } from "next/navigation";
import type { Metadata } from "next";

type ArticleData = {
  title: string;
  description: string;
  date: string;
  author: string;
  content: React.ReactNode;
};

const articles: Record<string, ArticleData> = {
  "what-is-factoring": {
    title: "ファクタリングとは？仕組み・種類・メリットをわかりやすく解説",
    description: "ファクタリングの基本的な仕組み、2社間・3社間の違い、メリット・デメリットを初心者向けにわかりやすく解説します。",
    date: "2026-03-01",
    author: "ファクタリング比較ナビ編集部",
    content: (
      <>
        <h2>ファクタリングとは</h2>
        <p>
          ファクタリングとは、企業が保有する売掛金（売掛債権）をファクタリング会社に売却し、
          支払期日前に現金化する資金調達方法です。銀行融資とは異なり「借入」ではないため、
          貸借対照表上の負債が増えず、信用情報にも影響しないのが大きな特徴です。
        </p>

        <h2>ファクタリングの種類</h2>
        <h3>2社間ファクタリング</h3>
        <p>
          利用者とファクタリング会社の2社間で契約する方式です。取引先にファクタリングの利用を
          知られることがなく、スピーディーに資金化できますが、手数料はやや高めです。
        </p>
        <h3>3社間ファクタリング</h3>
        <p>
          利用者・ファクタリング会社・取引先の3社間で契約する方式です。取引先の承諾が必要ですが、
          手数料が低く抑えられるメリットがあります。
        </p>

        <h2>ファクタリングのメリット</h2>
        <ul>
          <li>最短即日で資金調達が可能</li>
          <li>借入ではないため信用情報に影響しない</li>
          <li>赤字決算や税金滞納があっても利用可能</li>
          <li>担保・保証人が不要</li>
          <li>売掛先の信用力で審査されるため、自社の業績に左右されにくい</li>
        </ul>

        <h2>ファクタリングのデメリット</h2>
        <ul>
          <li>手数料がかかる（2%〜20%程度）</li>
          <li>売掛金の範囲内でしか資金調達できない</li>
          <li>悪質な業者も存在するため注意が必要</li>
        </ul>

        <h2>まとめ</h2>
        <p>
          ファクタリングは、急な資金需要に対応できる有効な資金調達手段です。
          ただし、手数料や業者の信頼性をしっかり確認することが重要です。
          当サイトの<a href="/ranking">ランキング</a>や<a href="/reviews">口コミ</a>を
          参考に、信頼できる業者を選びましょう。
        </p>
      </>
    ),
  },
  "how-to-choose": {
    title: "失敗しないファクタリング業者の選び方【7つのチェックポイント】",
    description: "手数料だけで選ぶと失敗する？信頼できるファクタリング業者を見極めるための7つのチェックポイントを解説。",
    date: "2026-03-05",
    author: "ファクタリング比較ナビ編集部",
    content: (
      <>
        <h2>業者選びで失敗しないために</h2>
        <p>
          ファクタリング業者は数多く存在し、サービス内容や手数料も千差万別です。
          手数料の安さだけで選んでしまうと、思わぬトラブルに巻き込まれることも。
          以下の7つのポイントをチェックして、信頼できる業者を選びましょう。
        </p>

        <h2>1. 手数料の透明性</h2>
        <p>手数料の範囲が明確に提示されているか確認しましょう。「1%〜」と極端に安い手数料を謳っている業者は要注意です。</p>

        <h2>2. 入金スピード</h2>
        <p>急ぎの資金需要がある場合、即日入金に対応しているかは重要なポイントです。</p>

        <h2>3. 運営会社の信頼性</h2>
        <p>会社の所在地、設立年数、資本金などを確認しましょう。公式サイトに会社概要が明記されているかも重要です。</p>

        <h2>4. 契約条件</h2>
        <p>償還請求権の有無（ノンリコースかリコースか）を必ず確認しましょう。</p>

        <h2>5. 口コミ・評判</h2>
        <p>実際に利用した方の<a href="/reviews">口コミ</a>は業者選びの重要な参考情報です。</p>

        <h2>6. 対応の丁寧さ</h2>
        <p>問い合わせ時の対応が丁寧かどうかも見極めのポイントです。</p>

        <h2>7. 必要書類の量</h2>
        <p>オンライン完結型は書類が少なく済む傾向にあり、スピード面でも有利です。</p>

        <h2>まとめ</h2>
        <p>
          業者選びは複数社を比較検討することが大切です。
          当サイトの<a href="/estimate">一括見積もり</a>を利用すれば、
          複数社の条件を簡単に比較できます。
        </p>
      </>
    ),
  },
};

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const article = articles[slug];
  if (!article) return {};
  return {
    title: article.title,
    description: article.description,
  };
}

export function generateStaticParams() {
  return Object.keys(articles).map((slug) => ({ slug }));
}

export default async function ArticlePage({ params }: Props) {
  const { slug } = await params;
  const article = articles[slug];
  if (!article) notFound();

  return (
    <ArticleLayout title={article.title} date={article.date} author={article.author}>
      {article.content}
    </ArticleLayout>
  );
}
