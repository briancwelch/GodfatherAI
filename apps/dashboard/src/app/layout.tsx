import type { Metadata } from "next";
import "bootstrap/dist/css/bootstrap.min.css";
import "./globals.css";
import "./bootstrap-theme.css";
import { ToastNotifications } from "../components/toast-notifications";

export const metadata: Metadata = {
  title: "The Godfather · Command Center",
  description: "Private administration for The Godfather control plane.",
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        {children}
        <ToastNotifications />
      </body>
    </html>
  );
}
