"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Search, MessageSquare, LayoutDashboard, LogOut, Wrench } from "lucide-react";
import { token } from "@/lib/api";
import clsx from "clsx";

const NAV = [
  { href: "/",       label: "搜索",    icon: Search },
  { href: "/chat",   label: "对话",    icon: MessageSquare },
  { href: "/admin",  label: "管理",    icon: LayoutDashboard },
];

export default function Navbar() {
  const path = usePathname();
  const router = useRouter();

  const logout = () => {
    token.clear();
    router.push("/auth");
  };

  return (
    <nav className="bg-white border-b border-gray-200 sticky top-0 z-50">
      <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 font-semibold text-gray-900">
          <Wrench className="w-5 h-5 text-brand-500" />
          <span>PartsMind</span>
          <span className="text-xs text-gray-400 font-normal hidden sm:inline">零配件智能搜索</span>
        </Link>

        {/* Nav links */}
        <div className="flex items-center gap-1">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
                path === href
                  ? "bg-brand-50 text-brand-600"
                  : "text-gray-600 hover:bg-gray-100"
              )}
            >
              <Icon className="w-4 h-4" />
              <span className="hidden sm:inline">{label}</span>
            </Link>
          ))}

          <button
            onClick={logout}
            className="ml-2 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-gray-500 hover:bg-gray-100 transition-colors"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </nav>
  );
}
