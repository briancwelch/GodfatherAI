import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "The Godfather · Command Center",
  description: "Local development shell for The Godfather Command Center.",
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
