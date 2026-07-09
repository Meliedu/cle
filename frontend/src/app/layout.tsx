import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";
import { headers } from "next/headers";
import { Hanken_Grotesk, Fraunces } from "next/font/google";
import { Analytics } from "@vercel/analytics/next";
import { Toaster } from "sonner";
import "./globals.css";
import { QueryProvider } from "@/components/providers/query-provider";

// Body / UI — Hanken Grotesk: a warm humanist grotesque, highly legible at
// small sizes, with more character than the default system/Inter stack.
const sans = Hanken_Grotesk({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

// Display — Fraunces: an editorial "old-style" variable serif (optical sizing +
// soft/wonk axes) that gives the honey palette literary warmth on hero and
// page titles. Used deliberately via `.font-display`, never for body UI.
const display = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
  axes: ["opsz", "SOFT", "WONK"],
});

export const metadata: Metadata = {
  title: "Meli · Checkpoint-centred course loop for HKUST CLE",
  description:
    "Meli turns course materials into active learning habits for students and low-friction teaching support for teachers — a reviewed checkpoint loop for HKUST Centre for Language Education.",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = await getLocale();
  const messages = await getMessages();
  // Reading the per-request nonce forces this layout into dynamic rendering
  // (required when the CSP carries a per-request nonce) so Next.js can stamp
  // the value on framework-emitted script tags.
  await headers();

  return (
    <html lang={locale} className={`${sans.variable} ${display.variable}`}>
      <body className="font-sans antialiased">
        <NextIntlClientProvider messages={messages}>
          <QueryProvider>{children}</QueryProvider>
        </NextIntlClientProvider>
        <Toaster
          position="top-center"
          richColors
          closeButton
          toastOptions={{
            style: {
              fontFamily: "var(--font-sans)",
              borderRadius: "var(--radius-lg)",
            },
          }}
        />
        <Analytics />
      </body>
    </html>
  );
}
