import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'atlc3 GUI',
  description: 'Web GUI for the atlc3 transmission-line calculator',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
