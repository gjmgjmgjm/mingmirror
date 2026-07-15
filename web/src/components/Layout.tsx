import { Link, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  ScrollText,
  Compass,
  Sparkles,
  Users,
  FlaskConical,
  CalendarDays,
  BookOpen,
  Target,
  Sun,
  Moon,
  Library,
} from "lucide-react";
import { useTheme } from "../contexts/ThemeContext";
import type { ReactNode } from "react";

interface LayoutProps {
  children: ReactNode;
}

const navItems = [
  { path: "/", label: "首页", icon: LayoutDashboard },
  { path: "/chart", label: "八字", icon: ScrollText },
  { path: "/ziwei", label: "紫微", icon: Sparkles },
  { path: "/qizheng", label: "七政", icon: Compass },
  { path: "/council", label: "议会", icon: Users },
  { path: "/sandbox", label: "沙盒", icon: FlaskConical },
  { path: "/calendar", label: "择日", icon: CalendarDays },
  { path: "/script", label: "剧本", icon: BookOpen },
  { path: "/events", label: "校准", icon: Target },
  { path: "/cases", label: "案例", icon: Library },
];

export default function Layout({ children }: LayoutProps) {
  const { theme, toggle } = useTheme();
  const location = useLocation();

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <div className="bg-clouds" aria-hidden="true" />
      <header className="fixed left-0 right-0 top-0 z-50 flex h-16 items-center justify-between border-b border-ink-300/20 bg-ink-100/90 px-4 backdrop-blur-md dark:border-ink-500/20 dark:bg-ink-900/90 md:px-6">
        <Link
          to="/"
          className="flex items-center gap-2 text-2xl text-ink-700 dark:text-ink-200"
        >
          <span className="font-display text-3xl text-vermilion">命镜</span>
          <span className="hidden text-sm font-medium tracking-wide sm:inline">
            MingMirror
          </span>
        </Link>
        <button
          type="button"
          onClick={toggle}
          className="rounded-xl p-2 text-ink-600 transition hover:bg-ink-200 dark:text-ink-300 dark:hover:bg-ink-800"
          aria-label={theme === "dark" ? "切换浅色模式" : "切换深色模式"}
        >
          {theme === "dark" ? (
            <Sun className="h-5 w-5" />
          ) : (
            <Moon className="h-5 w-5" />
          )}
        </button>
      </header>

      <nav className="fixed bottom-0 left-0 right-0 z-40 flex h-16 items-center gap-1 overflow-x-auto border-t border-ink-300/20 bg-ink-100/95 px-2 scrollbar-hide dark:border-ink-500/20 dark:bg-ink-900/95 md:bottom-auto md:top-16 md:h-[calc(100vh-4rem)] md:w-56 md:flex-col md:items-stretch md:justify-start md:overflow-visible md:border-r md:border-t-0 md:px-3 md:py-6">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active =
            item.path === "/chart"
              ? location.pathname === "/chart" || location.pathname === "/chart/yearly"
              : item.path === "/qizheng"
                ? location.pathname === "/qizheng" || location.pathname === "/qizheng/yearly"
                : location.pathname === item.path;
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`flex shrink-0 flex-col items-center gap-1 rounded-xl px-4 py-2 transition md:flex-row md:gap-3 md:px-4 md:py-3 ${
                active
                  ? "bg-vermilion/10 text-vermilion dark:bg-vermilion/20"
                  : "text-ink-500 hover:bg-ink-200/50 hover:text-ink-700 dark:text-ink-400 dark:hover:bg-ink-800/50 dark:hover:text-ink-200"
              }`}
            >
              <Icon className="h-5 w-5" />
              <span className="text-[10px] font-medium md:text-sm">
                {item.label}
              </span>
            </Link>
          );
        })}
      </nav>

      <main className="flex-1 px-4 pb-24 pt-20 md:ml-56 md:pb-8 md:pr-8">
        {children}
      </main>
    </div>
  );
}
