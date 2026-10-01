import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Aristotle — Live Reconciliation",
  description: "Capital Flywheel — live position reconciliation vs the Master Operating Plan",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
