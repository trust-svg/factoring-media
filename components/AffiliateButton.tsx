"use client";

declare global {
  interface Window {
    gtag?: (...args: unknown[]) => void;
  }
}

type AffiliateButtonProps = {
  href: string;
  company: string;
  slug: string;
  className?: string;
  children: React.ReactNode;
};

export function AffiliateButton({ href, company, slug, className, children }: AffiliateButtonProps) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className={className}
      onClick={() => {
        if (typeof window !== "undefined" && window.gtag) {
          window.gtag("event", "affiliate_click", {
            company,
            slug,
          });
        }
      }}
    >
      {children}
    </a>
  );
}
