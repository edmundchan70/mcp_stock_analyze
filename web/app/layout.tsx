import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Stock Scan Dashboard",
  description: "Run and review EP / VCP / BO scans",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-950 text-slate-100 antialiased">
        {children}
      </body>
    </html>
  );
}
