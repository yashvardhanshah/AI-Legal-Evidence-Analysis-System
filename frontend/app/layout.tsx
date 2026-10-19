import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Legal Evidence | Research workspace",
  description: "AI Legal Evidence Analysis System — academic development workspace",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
