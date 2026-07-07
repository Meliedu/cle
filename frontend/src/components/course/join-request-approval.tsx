"use client";

import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import { Check, Loader2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, StateBanner } from "@/components/patterns";
import {
  isNotPendingError,
  useApproveJoinRequest,
  useDenyJoinRequest,
  useJoinRequests,
  type JoinRequest,
} from "@/hooks/use-enrollment";

interface JoinRequestApprovalProps {
  readonly courseId: string;
}

type Translate = ReturnType<typeof useTranslations>;

/** Locale date for a request, e.g. "15 Jan 2026". */
function formatRequested(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** Two-letter initials for the avatar chip, falling back to the email. */
function initials(entry: JoinRequest): string {
  const source = entry.full_name?.trim() || entry.email;
  const parts = source.split(/\s+/).filter(Boolean);
  const chars =
    parts.length >= 2
      ? `${parts[0][0]}${parts[parts.length - 1][0]}`
      : source.slice(0, 2);
  return chars.toUpperCase();
}

/**
 * T033 — join-request approval. Lists pending enrollments awaiting the owning
 * instructor's decision (`useJoinRequests`, shared with the T031 pending count)
 * with per-row Approve / Deny actions. Approve moves the student into the
 * roster (`status → active`), deny rejects the request; both mutations
 * invalidate the pending list + roster so the row leaves this list on success.
 * A stale decision (someone approved in another tab) returns 409 `NOT_PENDING`
 * — treated as benign, we just show a soft notice and let the refetch drop the
 * row. Read-only until a teacher acts; empty state when nothing is pending.
 */
export function JoinRequestApproval({ courseId }: JoinRequestApprovalProps) {
  const t = useTranslations("teacher.enrollment.requests");
  const { data, isLoading, isError } = useJoinRequests(courseId);
  const [notice, setNotice] = useState<string | null>(null);

  const requests: readonly JoinRequest[] = data
    ? [...data].sort((a, b) => a.requested_at.localeCompare(b.requested_at))
    : [];

  return (
    <section className="space-y-4">
      <div className="space-y-1">
        <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
          {t("title")}
        </h2>
        <p className="text-[13px] text-[var(--color-text-secondary)]">
          {t("subtitle")}
        </p>
      </div>

      {notice ? (
        <StateBanner tone="waiting" title={t("stale.title")} reason={notice} />
      ) : null}

      {isError ? (
        <StateBanner
          tone="warning"
          title={t("error.title")}
          reason={t("error.reason")}
        />
      ) : isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full rounded-[var(--radius-md)]" />
          ))}
        </div>
      ) : requests.length === 0 ? (
        <EmptyState title={t("empty.title")} reason={t("empty.reason")} />
      ) : (
        <ul className="space-y-2.5">
          {requests.map((request) => (
            <RequestRow
              key={request.enrollment_id}
              courseId={courseId}
              request={request}
              onNotice={setNotice}
              t={t}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

interface RequestRowProps {
  readonly courseId: string;
  readonly request: JoinRequest;
  readonly onNotice: (message: string | null) => void;
  readonly t: Translate;
}

function RequestRow({ courseId, request, onNotice, t }: RequestRowProps) {
  const approve = useApproveJoinRequest(courseId);
  const deny = useDenyJoinRequest(courseId);
  const [error, setError] = useState<string | null>(null);

  const isBusy = approve.isPending || deny.isPending;

  const decide = useCallback(
    async (
      mutation: typeof approve,
      enrollmentId: string
    ): Promise<void> => {
      setError(null);
      onNotice(null);
      try {
        await mutation.mutateAsync(enrollmentId);
      } catch (err) {
        // A concurrent decision (already approved/denied elsewhere) is benign:
        // the invalidation already refetches the list, so nudge, don't alarm.
        if (isNotPendingError(err)) {
          onNotice(t("stale.reason"));
          return;
        }
        setError(t("actionError"));
      }
    },
    [onNotice, t]
  );

  return (
    <li className="flex flex-col gap-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        <span
          aria-hidden="true"
          className="flex size-9 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-light)] text-[11px] font-semibold text-[var(--color-primary)]"
        >
          {initials(request)}
        </span>
        <div className="min-w-0">
          <p className="truncate text-[13px] font-medium text-[var(--color-text)]">
            {request.full_name || t("noName")}
          </p>
          <p className="truncate text-[12px] text-[var(--color-text-secondary)]">
            {request.email}
          </p>
          <p className="text-[11px] text-[var(--color-text-muted)]">
            {t("requestedAt", { date: formatRequested(request.requested_at) })}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {error ? (
          <span role="alert" className="text-[12px] text-[var(--color-error)]">
            {error}
          </span>
        ) : null}
        <Button
          type="button"
          size="sm"
          disabled={isBusy}
          onClick={() => void decide(approve, request.enrollment_id)}
        >
          {approve.isPending ? (
            <Loader2 aria-hidden="true" className="animate-spin" />
          ) : (
            <Check aria-hidden="true" />
          )}
          {t("approve")}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={isBusy}
          onClick={() => void decide(deny, request.enrollment_id)}
        >
          {deny.isPending ? (
            <Loader2 aria-hidden="true" className="animate-spin" />
          ) : (
            <X aria-hidden="true" />
          )}
          {t("deny")}
        </Button>
      </div>
    </li>
  );
}
