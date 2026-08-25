import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Atlas Industrial Supply — AI Customer Service",
  description:
    "A synthetic industrial distributor with an ElevenLabs voice agent wired to real order, inventory and quoting APIs.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
