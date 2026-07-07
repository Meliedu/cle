import { Layers, ListChecks, MessageSquareHeart, type LucideIcon } from "lucide-react";

import type {
  Activity,
  ActivityConfig,
  ActivityFormat,
} from "@/hooks/use-activities";

/**
 * Static per-format metadata shared by the F4 builders, the F5 monitor, and the
 * F6 home. Keeps the `format → config key / icon / i18n stem` mapping in one
 * place so every activities surface reads it identically.
 */
export interface ActivityFormatMeta {
  readonly format: ActivityFormat;
  /** The `config` array key this format writes (`prompts | options | reactions`). */
  readonly configKey: "prompts" | "options" | "reactions";
  /** Decorative glyph for the format (always `aria-hidden`). */
  readonly Icon: LucideIcon;
  /** i18n key under `teacher.activities.formats.*` for the display name. */
  readonly labelKey: ActivityFormat;
}

export const ACTIVITY_FORMAT_META: Record<ActivityFormat, ActivityFormatMeta> = {
  swipe: {
    format: "swipe",
    configKey: "prompts",
    Icon: Layers,
    labelKey: "swipe",
  },
  vote: {
    format: "vote",
    configKey: "options",
    Icon: ListChecks,
    labelKey: "vote",
  },
  comment_reaction: {
    format: "comment_reaction",
    configKey: "reactions",
    Icon: MessageSquareHeart,
    labelKey: "comment_reaction",
  },
};

/** Ordered list of the three supported formats (builder tabs, home sections). */
export const ACTIVITY_FORMATS: readonly ActivityFormat[] = [
  "swipe",
  "vote",
  "comment_reaction",
];

/** Read the format's config list from an activity, tolerating a missing shape. */
export function readConfigList(activity: Activity): readonly string[] {
  const key = ACTIVITY_FORMAT_META[activity.format].configKey;
  const raw = (activity.config as Record<string, unknown>)[key];
  if (!Array.isArray(raw)) return [];
  return raw.filter((v): v is string => typeof v === "string");
}

/** Build a `config` payload for a format from its edited string list. */
export function buildConfig(
  format: ActivityFormat,
  list: readonly string[]
): ActivityConfig {
  const key = ACTIVITY_FORMAT_META[format].configKey;
  return { [key]: list } as ActivityConfig;
}
