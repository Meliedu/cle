import type { useTranslations } from "next-intl";

/** The coarse buckets the backend emits for `level_hint`. */
export const LEVEL_HINTS = ["foundation", "intermediate", "advanced"] as const;

/**
 * Map a server-computed `level_hint` bucket to its translated label so every
 * surface (S009 recommendation, S011 summary) shows the same wording. Falls
 * back to the raw hint (or a neutral label) for an unrecognized bucket.
 */
export function levelHintLabel(
  t: ReturnType<typeof useTranslations>,
  hint: string
): string {
  if ((LEVEL_HINTS as readonly string[]).includes(hint)) {
    return t(`recommendation.levels.${hint}`);
  }
  return hint || t("recommendation.levels.unknown");
}
