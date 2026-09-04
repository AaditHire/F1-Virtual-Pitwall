import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "F1 Virtual Pit Wall",
  description: "Cutoff-safe historical race replay and strategy analysis.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
