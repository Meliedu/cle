"use client";

import { useLocale } from "next-intl";

export function LanguageToggle() {
  const locale = useLocale();

  function switchLocale(newLocale: string) {
    document.cookie = `NEXT_LOCALE=${newLocale};path=/;max-age=31536000`;
    window.location.reload();
  }

  return (
    <button
      onClick={() => switchLocale(locale === "en" ? "zh-Hant" : "en")}
      className="rounded-[var(--radius-md)] px-2 py-1 text-sm font-medium text-[var(--color-text-muted)] transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)]"
    >
      {locale === "en" ? "\u7E41\u9AD4\u4E2D\u6587" : "English"}
    </button>
  );
}
