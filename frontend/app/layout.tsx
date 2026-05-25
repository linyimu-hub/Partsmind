import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PartsMind — 零配件智能搜索",
  description: "用 AI 快速找到汽车零配件，支持图片识别和自然语言问答",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh">
      <body>{children}</body>
    </html>
  );
}
