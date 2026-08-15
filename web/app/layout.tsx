import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";
import "./editorial-v2.css";
import "./editorial-workspaces.css";
import { SiteHeader } from "@/components/site-header";
import { loadSiteConfig } from "@/lib/server-api";
import { RouteTransition } from "@/components/route-transition";

export async function generateMetadata(): Promise<Metadata> {
  const config = await loadSiteConfig();
  return {
    title: {
      default: config.site_name,
      template: `%s｜${config.site_name}`,
    },
    description: config.intro_lines.join(" "),
    robots: {
      index: false,
      follow: false,
      noarchive: true,
      googleBot: {
        index: false,
        follow: false,
        noimageindex: true,
      },
    },
    icons: {
      icon: "/favicon.svg",
      shortcut: "/favicon.svg",
    },
  };
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const config = await loadSiteConfig();
  return (
    <html lang="zh-CN">
      <head>
        <Script src="/runtime-config.js" strategy="beforeInteractive" />
      </head>
      <body>
        <a className="skip-link" href="#main-content">
          跳到主要内容
        </a>
        <SiteHeader config={config} />
        <main id="main-content"><RouteTransition>{children}</RouteTransition></main>
      </body>
    </html>
  );
}
