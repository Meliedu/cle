"use client";

import { useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowLeft } from "lucide-react";

import { PageHeader, StateBanner } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api";
import {
  useActivityIntro,
  useSubmitActivityResponse,
  type ActivityResponsePayload,
  type ActivityResponseRecord,
} from "@/hooks/use-activities";

import { ActivityWaiting } from "./activity-waiting";
import { SwipeActivity } from "./swipe-activity";
import { VoteActivity } from "./vote-activity";
import { CommentReactionActivity } from "./comment-reaction-activity";
import {
  commentReactions,
  isActivityOpen,
  reactionEntries,
  swipePrompts,
  voteOptions,
} from "./activity-format";

interface ActivityRunnerProps {
  readonly courseId: string;
  readonly activityId: string;
}

/**
 * S053–S058 / S073 — the student activity flow orchestrator. Loads the activity
 * via the student-safe intro read (`useActivityIntro` → `GET /activities/{id}/intro`,
 * enrollment-scoped + `published`/`live` only) and submits per-format answers
 * (`useSubmitActivityResponse`),
 * folding the read + submit state into one focused, mobile-first screen:
 *
 *   loading → (read blocked / not-yet-open / `ACTIVITY_NOT_OPEN` 409) waiting
 *           → format interaction (swipe | vote | comment_reaction)
 *           → submitted confirmation + the student's own record.
 *
 * Every branch renders a designed state — never a blank div. A submit refused
 * with the typed `ACTIVITY_NOT_OPEN` code flips the whole screen to the waiting
 * state; any other submit error surfaces as a non-blocking banner.
 */
export function ActivityRunner({ courseId, activityId }: ActivityRunnerProps) {
  const t = useTranslations("student.activities.runner");
  const { data: activity, isLoading, isError } = useActivityIntro(activityId);
  const submit = useSubmitActivityResponse(activityId);

  const [record, setRecord] = useState<ActivityResponseRecord | null>(null);
  const [notOpen, setNotOpen] = useState(false);

  async function handleSubmit(
    payload: ActivityResponsePayload
  ): Promise<ActivityResponseRecord> {
    try {
      const result = await submit.mutateAsync({ payload });
      setRecord(result);
      return result;
    } catch (error) {
      if (error instanceof ApiError && error.code === "ACTIVITY_NOT_OPEN") {
        setNotOpen(true);
      }
      throw error;
    }
  }

  const backHref = `/student/courses/${courseId}/activities`;

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <PageHeader
        title={activity?.title ?? t("fallbackTitle")}
        breadcrumb={
          <Link
            href={backHref}
            className="inline-flex items-center gap-1 hover:text-[var(--color-text)]"
          >
            <ArrowLeft aria-hidden="true" className="size-3.5" />
            {t("back")}
          </Link>
        }
      />

      {isLoading ? (
        <div className="space-y-3" aria-hidden="true">
          <Skeleton className="h-24 w-full rounded-[var(--radius-xl)]" />
          <Skeleton className="h-12 w-full rounded-[var(--radius-lg)]" />
        </div>
      ) : notOpen || isError || !activity || !isActivityOpen(activity) ? (
        <ActivityWaiting />
      ) : (
        <div className="space-y-4">
          {record ? (
            <StateBanner
              tone="success"
              title={t("submittedTitle")}
              reason={t("submittedReason")}
            />
          ) : null}

          {submit.isError && !notOpen ? (
            <StateBanner
              tone="warning"
              title={t("errorTitle")}
              reason={submit.error?.message ?? t("errorReason")}
            />
          ) : null}

          {activity.format === "swipe" ? (
            <SwipeActivity
              prompts={swipePrompts(activity.config)}
              onSubmit={handleSubmit}
              isSubmitting={submit.isPending}
            />
          ) : activity.format === "vote" ? (
            <VoteActivity
              options={voteOptions(activity.config)}
              submittedChoice={choiceOf(record)}
              onSubmit={handleSubmit}
              isSubmitting={submit.isPending}
            />
          ) : (
            <CommentReactionActivity
              reactions={commentReactions(activity.config)}
              entries={reactionEntries(record?.payload)}
              onSubmit={handleSubmit}
              isSubmitting={submit.isPending}
            />
          )}
        </div>
      )}
    </div>
  );
}

/** The choice string persisted on a `vote` response record, if any. */
function choiceOf(record: ActivityResponseRecord | null): string | null {
  if (!record) return null;
  const choice = (record.payload as Record<string, unknown>).choice;
  return typeof choice === "string" ? choice : null;
}
