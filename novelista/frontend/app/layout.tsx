import "./globals.css";
import type { Metadata } from "next";
import { Providers } from "./providers";
import { SettingsTestBanner } from "@/components/SettingsTestBanner";

export const metadata: Metadata = {
  title: "Novelista",
  description: "Local-LLM novel generation.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>
        <Providers>
          <div className="min-h-screen">
            <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur sticky top-0 z-10">
              <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
                <a href="/" className="text-xl font-semibold tracking-tight">
                  <span className="text-accent">Novel</span>ista
                </a>
                <nav className="text-sm text-slate-400 space-x-4">
                  <a href="/" className="hover:text-slate-200">Dashboard</a>
                  <a href="/settings" className="hover:text-slate-200">Settings</a>
                </nav>
              </div>
            </header>
            <main className="max-w-6xl mx-auto px-6 py-8">{children}</main>
            <SettingsTestBanner />
          </div>
        </Providers>
      </body>
    </html>
  );
}
