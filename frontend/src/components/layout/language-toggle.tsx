"use client";

import { useLocale } from "next-intl";

export function LanguageToggle() {
  const locale = useLocale();

  function switchLocale(newLocale: string) {
    // SameSite=Lax stops the cookie riding cross-site requests; Secure keeps it
    // off plaintext http. encodeURIComponent guards the cookie value.
    const secure = window.location.protocol === "https:" ? ";Secure" : "";
    document.cookie = `NEXT_LOCALE=${encodeURIComponent(newLocale)};path=/;max-age=31536000;SameSite=Lax${secure}`;
    window.location.reload();
  }

  return (
    <button
      onClick={() => switchLocale(locale === "en" ? "zh-Hant" : "en")}
      className="inline-flex h-11 items-center rounded-[var(--radius-md)] px-3 text-sm font-medium text-[var(--color-text-muted)] transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)]"
    >
      {locale === "en" ? "\u7E41\u9AD4\u4E2D\u6587" : "English"}
    </button>
  );
}
