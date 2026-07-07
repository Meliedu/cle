"use client";

import { useTranslations } from "next-intl";

import { StateBanner } from "@/components/patterns";
import { ScorePolicyError } from "@/hooks/use-quizzes";
import { ApiError } from "@/lib/api";

interface ActivityPublishGateProps {
  /** The error thrown by `usePublishActivity`, or `null` when publish is clear. */
  readonly error: unknown;
}

/**
 * The activities-track publish gate banner (F4). Deliberately its OWN small
 * component — it does NOT import the teacher-quiz gate. It classifies a failed
 * `usePublishActivity` mutation into a designed `StateBanner tone="blocked"`:
 *
 *  - `ScorePolicyError` (422 `SCORE_POLICY_INCOMPLETE`) → lists the missing
 *    score fields the teacher must fill before a score-bearing activity ships.
 *  - 422 `ACTIVITY_CONFIG_INVALID` → the format config is empty / malformed.
 *  - 409 `ACTIVITY_NOT_PUBLISHABLE` → the activity is in a state that can't be
 *    published (already closed / archived).
 *  - anything else → a generic blocked banner with the server message.
 *
 * Renders nothing when `error` is null/undefined.
 */
export function ActivityPublishGate({ error }: ActivityPublishGateProps) {
  const t = useTranslations("teacher.activities.publish.gate");

  if (!error) return null;

  if (error instanceof ScorePolicyError) {
    const fields = error.missing.length > 0 ? error.missing : ["score_category_id"];
    return (
      <StateBanner
        tone="blocked"
        title={t("scorePolicy.title")}
        reason={t("scorePolicy.reason", {
          fields: fields.map((f) => scoreFieldLabel(t, f)).join(", "),
        })}
      />
    );
  }

  if (error instanceof ApiError) {
    if (error.code === "ACTIVITY_CONFIG_INVALID") {
      return (
        <StateBanner
          tone="blocked"
          title={t("configInvalid.title")}
          reason={t("configInvalid.reason")}
        />
      );
    }
    if (error.code === "ACTIVITY_NOT_PUBLISHABLE") {
      return (
        <StateBanner
          tone="blocked"
          title={t("notPublishable.title")}
          reason={t("notPublishable.reason")}
        />
      );
    }
    return (
      <StateBanner
        tone="blocked"
        title={t("generic.title")}
        reason={error.message || t("generic.reason")}
      />
    );
  }

  return (
    <StateBanner
      tone="blocked"
      title={t("generic.title")}
      reason={error instanceof Error ? error.message : t("generic.reason")}
    />
  );
}

/** Map a backend `missing` field id to its human label (falls back to raw id). */
function scoreFieldLabel(
  t: ReturnType<typeof useTranslations>,
  field: string
): string {
  const known: Record<string, string> = {
    score_category_id: t("scorePolicy.fields.score_category_id"),
    points: t("scorePolicy.fields.points"),
    grading_mode: t("scorePolicy.fields.grading_mode"),
    late_rule: t("scorePolicy.fields.late_rule"),
    due_at: t("scorePolicy.fields.due_at"),
    close_at: t("scorePolicy.fields.close_at"),
  };
  return known[field] ?? field;
}
