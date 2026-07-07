"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { ListTodo, type LucideIcon } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, StateBanner } from "@/components/patterns";
import { StatusChip } from "@/components/course/session-status";
import { useChecklist, type ChecklistItem } from "@/hooks/use-work-items";

import { sourceKindIcon } from "./source-kind";
import { checklistBucket, workItemTone, type ChecklistBucket } from "./work-item-status";

interface StudentChecklistProps {
  readonly courseId: string;
}

/** Locale date + time for a due/close stamp, e.g. "Fri, 10 Jul · 23:59". */
function formatWhen(iso: string): string {
  const date = new Date(iso);
  const day = date.toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
  const time = date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${day} · ${time}`;
}

const BUCKET_ORDER: readonly ChecklistBucket[] = ["open", "missed", "done"];

/** Sort a bucket's items by their due/close time, undated last. */
function byDue(a: ChecklistItem, b: ChecklistItem): number {
  const at = a.due_at ?? a.close_at;
  const bt = b.due_at ?? b.close_at;
  if (at && bt) return at.localeCompare(bt);
  if (at) return -1;
  if (bt) return 1;
  return 0;
}

/**
 * S024 — student checklist. Reads the work-item spine (`useChecklist`) and
 * groups items into open / missed / done buckets, each row carrying one status
 * chip (a single tone per `work_item_progress.status`, shared via
 * `workItemTone`). This is the read spine — the same source the overview
 * next-action and the calendar overlay draw from.
 */
export function StudentChecklist({ courseId }: StudentChecklistProps) {
  const t = useTranslations("student.checklist");
  const { data, isLoading, isError } = useChecklist(courseId);

  const buckets = useMemo(() => {
    const map: Record<ChecklistBucket, ChecklistItem[]> = {
      open: [],
      missed: [],
      done: [],
    };
    for (const item of data ?? []) map[checklistBucket(item.status)].push(item);
    for (const key of BUCKET_ORDER) map[key].sort(byDue);
    return map;
  }, [data]);

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full rounded-[var(--radius-xl)]" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <StateBanner
        tone="warning"
        title={t("error.title")}
        reason={t("error.reason")}
      />
    );
  }

  const total = (data ?? []).length;
  if (total === 0) {
    return (
      <EmptyState
        icon={ListTodo}
        title={t("empty.title")}
        reason={t("empty.reason")}
      />
    );
  }

  return (
    <section className="space-y-6">
      <div className="space-y-1">
        <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
          {t("title")}
        </h2>
        <p className="text-[13px] text-[var(--color-text-secondary)]">
          {t("summary", {
            open: buckets.open.length,
            done: buckets.done.length,
          })}
        </p>
      </div>

      {BUCKET_ORDER.map((bucket) =>
        buckets[bucket].length > 0 ? (
          <ChecklistGroup
            key={bucket}
            heading={t(`groups.${bucket}`)}
            items={buckets[bucket]}
          />
        ) : null
      )}
    </section>
  );
}

interface ChecklistGroupProps {
  readonly heading: string;
  readonly items: readonly ChecklistItem[];
}

function ChecklistGroup({ heading, items }: ChecklistGroupProps) {
  return (
    <div className="space-y-2">
      <h3 className="text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        {heading}
      </h3>
      <ul className="space-y-2">
        {items.map((item) => (
          <ChecklistRow key={item.id} item={item} />
        ))}
      </ul>
    </div>
  );
}

function ChecklistRow({ item }: { readonly item: ChecklistItem }) {
  const t = useTranslations("student.checklist");
  const tk = useTranslations("student.checklist.kind");
  const ts = useTranslations("student.checklist.status");
  const Icon: LucideIcon = sourceKindIcon(item.source_kind);
  const when = item.due_at ?? item.close_at;

  return (
    <li className="flex items-center gap-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
      <div className="flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary)]">
        <Icon aria-hidden="true" strokeWidth={1.85} className="size-5" />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            {tk(item.source_kind)}
          </span>
          {item.required ? (
            <span className="text-[11px] font-medium text-[var(--color-primary)]">
              {t("required")}
            </span>
          ) : null}
        </div>
        <p className="truncate text-[14px] font-semibold text-[var(--color-text)]">
          {item.title}
        </p>
        {when ? (
          <p className="truncate text-[12px] text-[var(--color-text-muted)]">
            {t("dueWhen", { when: formatWhen(when) })}
          </p>
        ) : null}
      </div>

      <StatusChip
        tone={workItemTone(item.status)}
        label={ts(item.status)}
        className="self-start"
      />
    </li>
  );
}
