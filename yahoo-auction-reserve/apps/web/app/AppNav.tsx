"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// ナビは PC の左固定サイドと、モバイルの下タブで同じ定義を使う。
// 2箇所に書き分けると片方だけ増える(実際に「設定」がPCにしか無い状態が起きる)。
const ITEMS = [
  { href: "/dashboard", label: "予約", icon: ClockIcon },
  { href: "/reservations/new", label: "追加", icon: PlusIcon },
  { href: "/watchlist", label: "ウォッチ", icon: StarIcon },
  { href: "/settings", label: "設定", icon: GearIcon },
] as const;

/** /settings/yahoo にいるときも「設定」を現在地にする(前方一致)。 */
function isCurrent(pathname: string, href: string): boolean {
  if (href === "/reservations/new") return pathname === href;
  if (href === "/dashboard") return pathname === href || pathname.startsWith("/reservations/");
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function SideNav({ email }: { email: string }) {
  const pathname = usePathname();
  return (
    <nav className="sidenav" aria-label="メインナビゲーション">
      <Link href="/dashboard" className="brand">
        ヤフオク入札予約
      </Link>
      {ITEMS.map(({ href, label, icon: Icon }) => (
        <Link
          key={href}
          href={href}
          className="nav"
          aria-current={isCurrent(pathname, href) ? "page" : undefined}
        >
          <Icon />
          {label === "追加" ? "新規予約" : label === "予約" ? "予約一覧" : label}
        </Link>
      ))}
      <div className="foot">{email}</div>
    </nav>
  );
}

export function TabBar() {
  const pathname = usePathname();
  return (
    <nav className="tabbar" aria-label="メインナビゲーション">
      {ITEMS.map(({ href, label, icon: Icon }) => (
        <Link
          key={href}
          href={href}
          aria-current={isCurrent(pathname, href) ? "page" : undefined}
        >
          <span className="ico" aria-hidden="true">
            <Icon />
          </span>
          {label}
        </Link>
      ))}
    </nav>
  );
}

// アイコンは currentColor の細線。絵文字だと OS によって色と字面が変わり、
// 現在地の色分けが効かなくなる。
function svgProps() {
  return {
    width: 20,
    height: 20,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.6,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
}

function ClockIcon() {
  return (
    <svg {...svgProps()}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg {...svgProps()}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function StarIcon() {
  return (
    <svg {...svgProps()}>
      <path d="M12 4.5l2.3 4.9 5.2.7-3.8 3.7.9 5.2-4.6-2.5-4.6 2.5.9-5.2L4.5 10l5.2-.7z" />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg {...svgProps()}>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3.5v2M12 18.5v2M20.5 12h-2M5.5 12h-2M17.8 6.2l-1.4 1.4M7.6 16.4l-1.4 1.4M17.8 17.8l-1.4-1.4M7.6 7.6L6.2 6.2" />
    </svg>
  );
}
