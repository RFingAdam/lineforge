import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://github.com/RFingAdam/lineforge"),
  title: "lineforge — Transmission Line Calculator",
  description:
    "Open-source MCP-enabled transmission-line calculator with closed-form, bitmap, and Faraday solvers.",
  openGraph: {
    siteName: "lineforge",
    title: "lineforge — Transmission Line Calculator",
    description:
      "Open-source MCP-enabled transmission-line calculator with closed-form, bitmap, and Faraday solvers.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="min-h-screen bg-canvas text-slate-100 antialiased font-display">
        {children}
      </body>
    </html>
  );
}
