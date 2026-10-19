import type { Metadata } from "next";
import "./globals.css";
import { Navbar } from "@/components/Navbar";

export const metadata: Metadata = {
  title: "Golf Swing Lab — AI 高爾夫揮桿分析實驗室",
  description:
    "練習場長影片自動切球、2D 骨架追蹤、可解釋 5 子分數評分、雙球同步比較與精選短片匯出",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-Hant">
      <body className="min-h-screen bg-[#090d11] text-gray-100 antialiased">
        <Navbar />
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
