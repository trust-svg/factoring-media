import Link from "next/link";

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
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm hover:shadow-md transition-shadow overflow-hidden">
      {isRecommended && (
        <div className="bg-green text-white text-xs font-bold px-4 py-1 text-center">
          おすすめ
        </div>
      )}
      <div className="p-5">
        <div className="flex items-start justify-between mb-3">
          <div>
            {rankingOrder && (
              <span className="text-xs font-bold text-navy bg-gray-100 px-2 py-1 rounded mr-2">
                #{rankingOrder}
              </span>
            )}
            <h3 className="text-lg font-bold text-navy inline">{name}</h3>
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

        <div className="grid grid-cols-2 gap-2 mb-4 text-sm">
          {fee && (
            <div className="bg-gray-50 rounded-lg px-3 py-2">
              <span className="text-gray-400 text-xs block">手数料</span>
              <span className="font-bold text-navy">{fee}</span>
            </div>
          )}
          {depositSpeed && (
            <div className="bg-gray-50 rounded-lg px-3 py-2">
              <span className="text-gray-400 text-xs block">入金速度</span>
              <span className="font-bold text-navy">{depositSpeed}</span>
            </div>
          )}
        </div>

        <div className="flex flex-wrap gap-1.5 mb-4">
          {features.slice(0, 4).map((feature) => (
            <span
              key={feature}
              className="text-xs bg-navy/5 text-navy px-2.5 py-1 rounded-full"
            >
              {feature}
            </span>
          ))}
        </div>

        <div className="flex gap-2">
          <Link
            href={`/companies/${slug}`}
            className="flex-1 text-center text-sm border border-navy text-navy py-2.5 rounded-lg font-medium hover:bg-navy hover:text-white transition-colors"
          >
            詳細を見る
          </Link>
          {affiliateUrl ? (
            <a
              href={affiliateUrl}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="flex-1 text-center text-sm bg-green text-white py-2.5 rounded-lg font-bold hover:bg-green-dark transition-colors"
              onClick={() => {
                if (typeof window !== "undefined" && window.gtag) {
                  window.gtag("event", "affiliate_click", {
                    company: name,
                    slug,
                  });
                }
              }}
            >
              公式サイトを見る
            </a>
          ) : (
            <a
              href={`/estimate`}
              className="flex-1 text-center text-sm bg-green text-white py-2.5 rounded-lg font-bold hover:bg-green-dark transition-colors"
            >
              無料見積もり
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
