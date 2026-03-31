import Link from "next/link";
import Image from "next/image";

declare global {
  interface Window {
    gtag?: (...args: unknown[]) => void;
  }
}

type CompanyCardProps = {
  slug: string;
  name: string;
  description: string;
  fee: string | null;
  depositSpeed: string | null;
  rating: number | null;
  reviewCount: number;
  features: string[];
  isRecommended: boolean;
  affiliateUrl: string | null;
  rankingOrder: number | null;
};

const medalColors: Record<number, { bg: string; text: string; border: string }> = {
  1: { bg: "bg-amber-400", text: "text-amber-900", border: "border-amber-400" },
  2: { bg: "bg-gray-300", text: "text-gray-700", border: "border-gray-300" },
  3: { bg: "bg-amber-600", text: "text-amber-100", border: "border-amber-600" },
};

export function CompanyCard({
  slug,
  name,
  description,
  fee,
  depositSpeed,
  rating,
  reviewCount,
  features,
  isRecommended,
  affiliateUrl,
  rankingOrder,
}: CompanyCardProps) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm card-hover overflow-hidden h-full flex flex-col">
      {features.length > 0 && (
        <div className="bg-primary text-white text-xs font-bold px-4 py-1.5 text-center">
          {features[0]}
        </div>
      )}
      <div className="p-5 flex-1 flex flex-col">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2">
            {rankingOrder && rankingOrder <= 3 ? (
              <Image
                src={`/images/rank-${rankingOrder}.png`}
                alt={`第${rankingOrder}位`}
                width={36}
                height={36}
                className="shrink-0"
              />
            ) : rankingOrder ? (
              <div className="w-9 h-9 bg-primary/10 rounded-full flex items-center justify-center shrink-0">
                <span className="text-sm font-bold text-primary">{rankingOrder}</span>
              </div>
            ) : null}
            <h3 className="text-base font-bold text-primary-darker whitespace-nowrap">{name}</h3>
          </div>
          {rating && (
            <div className="flex items-center gap-1 shrink-0">
              <Stars rating={rating} />
              <span className="text-sm font-bold text-gray-700">{rating.toFixed(1)}</span>
              <span className="text-xs text-gray-400">({reviewCount}件)</span>
            </div>
          )}
        </div>

        <p className="text-sm text-gray-600 mb-4 line-clamp-2">{description}</p>

        <div className="grid grid-cols-2 gap-2 mb-4">
          {fee && (
            <div className="bg-primary/5 rounded-lg px-3 py-2.5 flex items-center gap-2">
              <svg className="w-4 h-4 text-primary shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <span className="text-[10px] text-gray-400 block">手数料</span>
                <span className="font-bold text-primary text-sm">{fee}</span>
              </div>
            </div>
          )}
          {depositSpeed && (
            <div className="bg-secondary/5 rounded-lg px-3 py-2.5 flex items-center gap-2">
              <svg className="w-4 h-4 text-secondary shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              <div>
                <span className="text-[10px] text-gray-400 block">入金速度</span>
                <span className="font-bold text-secondary text-sm">{depositSpeed}</span>
              </div>
            </div>
          )}
        </div>

        <div className="flex flex-wrap gap-1.5 mb-4">
          {features.slice(0, 4).map((feature) => (
            <span
              key={feature}
              className="text-xs bg-primary/5 text-primary border border-primary/15 px-2.5 py-1 rounded-full font-medium"
            >
              {feature}
            </span>
          ))}
        </div>

        <div className="flex gap-2 mt-auto">
          <Link
            href={`/companies/${slug}`}
            className="flex-1 text-center text-sm border-2 border-primary text-primary py-2.5 rounded-lg font-bold hover:bg-primary hover:text-white transition-colors"
          >
            詳細を見る
          </Link>
          {affiliateUrl ? (
            <a
              href={affiliateUrl}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="flex-1 text-center text-sm bg-cta text-white py-2.5 rounded-lg font-bold hover:bg-cta-dark transition-colors shadow-md"
              onClick={() => {
                if (typeof window !== "undefined" && window.gtag) {
                  window.gtag("event", "affiliate_click", {
                    company: name,
                    slug,
                  });
                }
              }}
            >
              公式サイトへ &rarr;
            </a>
          ) : (
            <a
              href="/estimate"
              className="flex-1 text-center text-sm bg-cta text-white py-2.5 rounded-lg font-bold hover:bg-cta-dark transition-colors shadow-md"
            >
              無料見積もり &rarr;
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

export function Stars({ rating, size = "sm" }: { rating: number; size?: "sm" | "lg" }) {
  const stars = [];
  const full = Math.floor(rating);
  const hasHalf = rating - full >= 0.3;
  const sizeClass = size === "lg" ? "w-5 h-5" : "w-4 h-4";

  for (let i = 0; i < 5; i++) {
    if (i < full) {
      stars.push(
        <svg key={i} className={`${sizeClass} text-star`} fill="currentColor" viewBox="0 0 20 20">
          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
        </svg>
      );
    } else if (i === full && hasHalf) {
      stars.push(
        <svg key={i} className={`${sizeClass} text-star`} fill="currentColor" viewBox="0 0 20 20">
          <defs>
            <linearGradient id={`half-${i}`}>
              <stop offset="50%" stopColor="currentColor" />
              <stop offset="50%" stopColor="#e2e8f0" />
            </linearGradient>
          </defs>
          <path fill={`url(#half-${i})`} d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
        </svg>
      );
    } else {
      stars.push(
        <svg key={i} className={`${sizeClass} text-gray-200`} fill="currentColor" viewBox="0 0 20 20">
          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
        </svg>
      );
    }
  }
  return <div className="flex">{stars}</div>;
}
