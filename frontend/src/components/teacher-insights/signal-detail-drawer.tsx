"use client";

import { useTranslations } from "next-intl";
import {
  Dialog as DialogPrimitive,
} from "@base-ui/react/dialog";
import {
  Eye,
  FileSearch,
  Lightbulb,
  MapPin,
  ShieldAlert,
  Target,
  Users,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StateBanner } from "@/components/patterns";
import { useSignal, useEvidenceSource } from "@/hooks/use-insights";

import { outcomeToneClass } from "./insights-format";

/**
 * T077 — signal detail drawer. A right-anchored modal panel that opens a single
 * signal (`learning_note`) over `useSignal`, plus the raw learning-event it
 * traces back to over `useEvidenceSource` (the first `source_event_ids` entry).
 *
 * Built on the shared base-ui Dialog (Escape / backdrop / focus for free),
 * mirroring `calendar/event-detail-drawer.tsx`. The instructor sees content for
 * BOTH cohort (`user_id === null`) and individual signals; the backend only
 * withholds content while a note is `waiting_for_review`, which the drawer
 * renders as the designed waiting state (never a raw AI draft).
 */

interface SignalDetailDrawerProps {
  /** The signal (learning-note) id to open, or `null` when the drawer is closed. */
  readonly signalId: string | null;
  readonly onClose: () => void;
}

export function SignalDetailDrawer({ signalId, onClose }: SignalDetailDrawerProps) {
  const t = useTranslations("teacher.insights");
  const open = signalId !== null;

  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop className="fixed inset-0 z-50 bg-[oklch(20%_0.01_50/0.28)] duration-[var(--duration-fast)] data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0 motion-reduce:animate-none" />
        <DialogPrimitive.Popup
          data-slot="signal-detail-drawer"
          className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col gap-5 overflow-y-auto border-l border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-[var(--shadow-xl)] outline-none duration-[var(--duration-fast)] data-open:animate-in data-open:slide-in-from-right-6 data-closed:animate-out data-closed:slide-out-to-right-6 motion-reduce:animate-none"
        >
          <header className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--color-primary-light)] text-[var(--color-primary)]">
                <FileSearch aria-hidden="true" strokeWidth={1.85} className="size-4.5" />
              </span>
              <DialogPrimitive.Title className="text-[16px] font-semibold tracking-tight text-[var(--color-text)]">
                {t("drawer.title")}
              </DialogPrimitive.Title>
            </div>
            <DialogPrimitive.Close
              render={<Button variant="ghost" size="sm" />}
              onClick={onClose}
            >
              {t("drawer.close")}
            </DialogPrimitive.Close>
          </header>

          {open ? <DrawerBody signalId={signalId} /> : null}
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

function DrawerBody({ signalId }: { readonly signalId: string }) {
  const t = useTranslations("teacher.insights");
  const { data: signal, isLoading, isError } = useSignal(signalId);

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  if (isError || !signal) {
    return (
      <StateBanner
        tone="warning"
        title={t("drawer.loadError")}
        reason={t("loadErrorReason")}
      />
    );
  }

  const isCohort = signal.user_id === null;
  const eventId = signal.source_event_ids[0] ?? null;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--color-surface-hover)] px-2.5 py-1 text-[11px] font-medium text-[var(--color-text-secondary)]">
          {isCohort ? (
            <Users aria-hidden="true" className="size-3" />
          ) : (
            <Target aria-hidden="true" className="size-3" />
          )}
          {isCohort ? t("drawer.scopeCohort") : t("drawer.scopeStudent")}
        </span>
        {signal.outcome_status ? (
          <span
            className={cn(
              "rounded-full px-2.5 py-1 text-[11px] font-medium",
              outcomeToneClass(signal.outcome_status)
            )}
          >
            {t(`outcomeStatus.${signal.outcome_status}`)}
          </span>
        ) : null}
      </div>

      {signal.waiting_for_review ? (
        <StateBanner
          tone="waiting"
          title={t("drawer.waitingTitle")}
          reason={t("drawer.waitingReason")}
        />
      ) : (
        <div className="space-y-4">
          <DetailBlock icon={Eye} label={t("drawer.observed")}>
            {signal.observed_signal ?? "—"}
          </DetailBlock>
          {signal.draft_interpretation ? (
            <DetailBlock icon={Lightbulb} label={t("drawer.interpretation")}>
              {signal.draft_interpretation}
            </DetailBlock>
          ) : null}
          {signal.limitation_note ? (
            <DetailBlock icon={ShieldAlert} label={t("drawer.limitation")}>
              {signal.limitation_note}
            </DetailBlock>
          ) : null}
          {signal.context_anchor ? (
            <DetailBlock icon={MapPin} label={t("drawer.anchor")}>
              {typeof signal.context_anchor === "string"
                ? signal.context_anchor
                : JSON.stringify(signal.context_anchor)}
            </DetailBlock>
          ) : null}
        </div>
      )}

      <EvidenceSection eventId={eventId} />
    </div>
  );
}

interface DetailBlockProps {
  readonly icon: typeof Eye;
  readonly label: string;
  readonly children: React.ReactNode;
}

function DetailBlock({ icon: Icon, label, children }: DetailBlockProps) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        <Icon aria-hidden="true" strokeWidth={1.85} className="size-3.5" />
        {label}
      </div>
      <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
        {children}
      </p>
    </div>
  );
}

/**
 * Inline "where this came from" block over `useEvidenceSource`. F6 extends the
 * standalone `EvidenceSourceView` for the full T078 panel; here it stays a
 * compact summary within the drawer.
 */
function EvidenceSection({ eventId }: { readonly eventId: string | null }) {
  const t = useTranslations("teacher.insights");
  const { data: source, isLoading } = useEvidenceSource(eventId);

  if (eventId === null) {
    return (
      <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] p-3 text-[12px] text-[var(--color-text-muted)]">
        {t("evidence.empty")}
      </div>
    );
  }

  return (
    <div className="space-y-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] p-4">
      <p className="text-[12px] font-semibold text-[var(--color-text)]">
        {t("evidence.title")}
      </p>
      {isLoading || !source ? (
        <Skeleton className="h-12 w-full" />
      ) : (
        <dl className="grid grid-cols-2 gap-3 text-[12px]">
          <SourceRow label={t("evidence.source")}>
            {t.has(`evidence.sourceKind.${source.source_kind}`)
              ? t(`evidence.sourceKind.${source.source_kind}`)
              : source.source_kind}
          </SourceRow>
          <SourceRow label={t("evidence.stage")}>{source.stage}</SourceRow>
          {source.context_anchor ? (
            <SourceRow label={t("evidence.anchor")}>
              {typeof source.context_anchor === "string"
                ? source.context_anchor
                : JSON.stringify(source.context_anchor)}
            </SourceRow>
          ) : null}
        </dl>
      )}
    </div>
  );
}

function SourceRow({
  label,
  children,
}: {
  readonly label: string;
  readonly children: React.ReactNode;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[var(--color-text-muted)]">{label}</dt>
      <dd className="mt-0.5 truncate font-medium text-[var(--color-text)]">
        {children}
      </dd>
    </div>
  );
}
