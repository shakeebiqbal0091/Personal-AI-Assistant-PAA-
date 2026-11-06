
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PAA | Personal AI Assistant",
  description:
    "Your intelligent personal assistant for everyday life, tasks, and productivity.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}