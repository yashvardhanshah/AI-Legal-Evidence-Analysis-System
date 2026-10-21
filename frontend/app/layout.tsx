import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LEXISCOPE | Legal Investigation Intelligence",
  description: "Private, source-grounded legal investigation and evidence review",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
