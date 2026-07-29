import { getRequestConfig } from "next-intl/server";
import { cookies } from "next/headers";

import en from "../../messages/en.json";

type Messages = Record<string, unknown>;

const DEFAULT_LOCALE = "en";
const SUPPORTED_LOCALES = new Set(["en", "zh-Hant"]);

/**
 * Merge a locale's messages over the English base.
 *
 * Translation coverage is incomplete by design: locales land key-by-key as
 * copy is reviewed. Without this merge, next-intl resolves a missing key to an
 * error, so a partially translated namespace takes the whole screen down. The
 * release contract requires copy safety across locales, so an untranslated
 * string falls back to English rather than failing.
 *
 * Only plain objects recurse; arrays and scalars are replaced wholesale so a
 * translated list never blends with the English one.
 */
function withFallback(base: Messages, override: Messages): Messages {
  const merged: Messages = { ...base };
  for (const [key, value] of Object.entries(override)) {
    const existing = merged[key];
    if (isPlainObject(existing) && isPlainObject(value)) {
      merged[key] = withFallback(existing, value);
    } else if (value !== undefined && value !== null && value !== "") {
      merged[key] = value;
    }
  }
  return merged;
}

function isPlainObject(value: unknown): value is Messages {
  return (
    typeof value === "object" && value !== null && !Array.isArray(value)
  );
}

export default getRequestConfig(async () => {
  const cookieStore = await cookies();
  const requested = cookieStore.get("NEXT_LOCALE")?.value;
  const locale =
    requested && SUPPORTED_LOCALES.has(requested) ? requested : DEFAULT_LOCALE;

  if (locale === DEFAULT_LOCALE) {
    return { locale, messages: en as Messages };
  }

  const localeMessages = (await import(`../../messages/${locale}.json`))
    .default as Messages;

  return {
    locale,
    messages: withFallback(en as Messages, localeMessages),
  };
});
