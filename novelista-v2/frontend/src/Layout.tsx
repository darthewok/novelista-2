import { Link, Outlet } from "react-router-dom";
import { SettingsTestBanner } from "@/components/SettingsTestBanner";

export default function Layout() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link to="/" className="text-xl font-semibold tracking-tight">
            <span className="text-accent">Novel</span>ista
          </Link>
          <nav className="text-sm text-slate-400 space-x-4">
            <Link to="/" className="hover:text-slate-200">Dashboard</Link>
            <Link to="/settings" className="hover:text-slate-200">Settings</Link>
          </nav>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-6 py-8"><Outlet /></main>
      <SettingsTestBanner />
    </div>
  );
}
