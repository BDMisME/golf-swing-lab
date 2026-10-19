"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { clearAuthToken, getAuthToken } from "@/lib/api";

export function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const [hasToken, setHasToken] = useState(false);

  useEffect(() => {
    setHasToken(Boolean(getAuthToken()));
  }, [pathname]);

  const handleLogout = () => {
    clearAuthToken();
    setHasToken(false);
    router.push("/login");
  };

  const navItems = [
    { href: "/", label: "總覽" },
    { href: "/sessions/new", label: "新增練習上傳" },
    { href: "/exports", label: "匯出中心" },
    { href: "/settings", label: "評分與設定" },
  ];

  return (
    <header className="sticky top-0 z-40 border-b border-emerald-900/60 bg-[#0c1318]/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-600 font-bold text-white shadow">
            G
          </span>
          <div>
            <div className="text-base font-bold tracking-tight text-white">
              Golf Swing Lab
            </div>
            <div className="text-[11px] text-emerald-400">
              2D DTL 高爾夫練習場自動切球與動作實驗室
            </div>
          </div>
        </Link>

        <nav className="flex items-center gap-2 sm:gap-4">
          {navItems.map((item) => {
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-lg px-3 py-1.5 text-xs sm:text-sm font-medium transition ${
                  active
                    ? "bg-emerald-600/20 text-emerald-300 border border-emerald-500/40"
                    : "text-gray-300 hover:bg-white/5 hover:text-white"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
          {hasToken ? (
            <button
              onClick={handleLogout}
              className="rounded-lg border border-gray-700 px-2.5 py-1 text-xs text-gray-300 hover:border-red-500/50 hover:text-red-300"
            >
              登出
            </button>
          ) : (
            <Link
              href="/login"
              className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500"
            >
              登入
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
