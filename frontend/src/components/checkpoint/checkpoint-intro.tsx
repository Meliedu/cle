"use client";

import { CheckCircle2, ClipboardList, Clock, ListChecks } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import type { CheckpointIntro as CheckpointIntroData } from "@/hooks/use-checkpoints";

interface CheckpointIntroProps {
  readonly intro: CheckpointIntroData;
  /** Begin answering the cards (advances to S035). */
  readonly onStart: () => void;
  /** Leave the checkpoint (back to the session / courses). */
  readonly onBack: () => void;
}

/**
 * S034 — the checkpoint intro. A mobile-first single-column summary: the
 * checkpoint title, a "ready" chip, the list of review points the student is
 * about to answer, and the key facts (card count, attendance-on-submit, close
 * time). The primary CTA begins the card flow. Reads only live (non-removed)
 * cards from the intro payload.
 */
export function CheckpointIntro({ intro, onStart, onBack }: CheckpointIntroProps) {
  const t = useTranslations("student.checkpoint.intro");
  const format = useFormatter();
  const cardCount = intro.cards.length;

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
          {t("eyebrow")}
        </p>
        <h1 className="text-[22px] font-semibold leading-tight tracking-tight text-[var(--color-text)]">
          {intro.title}
        </h1>
        <span className="inline-flex items-center gap-1.5 rounded-[var(--radius-pill)] border border-[var(--color-success)]/40 bg-[var(--color-success-light)] px-2.5 py-1 text-[12px] font-medium text-[var(--color-success)]">
          <CheckCircle2 aria-hidden="true" className="size-3.5" />
          {t("readyChip")}
        </span>
      </div>

      <section className="space-y-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <h2 className="text-[14px] font-semibold tracking-tight text-[var(--color-text)]">
          {t("includes")}
        </h2>
        <ul className="space-y-2">
          {intro.cards.map((card, i) => (
            <li
              key={card.id}
              className="flex items-start gap-2.5 text-[14px] leading-snug text-[var(--color-text-secondary)]"
            >
              <span
                aria-hidden="true"
                className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-[var(--color-surface-hover)] text-[11px] font-semibold text-[var(--color-text-muted)]"
              >
                {i + 1}
              </span>
              {card.prompt}
            </li>
          ))}
        </ul>
      </section>

      <dl className="grid gap-2.5">
        <MetaRow icon={ListChecks} label={t("metaCards", { count: cardCount })} />
        <MetaRow icon={ClipboardList} label={t("metaAttendance")} />
        {intro.close_at ? (
          <MetaRow
            icon={Clock}
            label={t("metaCloses", {
              time: format.dateTime(new Date(intro.close_at), {
                hour: "numeric",
                minute: "2-digit",
              }),
            })}
          />
        ) : null}
      </dl>

      <div className="flex flex-col gap-2">
        <Button type="button" size="lg" onClick={onStart}>
          {t("start")}
        </Button>
        <Button type="button" size="lg" variant="ghost" onClick={onBack}>
          {t("back")}
        </Button>
      </div>
    </div>
  );
}

function MetaRow({
  icon: Icon,
  label,
}: {
  readonly icon: typeof Clock;
  readonly label: string;
}) {
  return (
    <div className="flex items-center gap-2.5 text-[13px] text-[var(--color-text-secondary)]">
      <Icon
        aria-hidden="true"
        strokeWidth={1.85}
        className="size-4 shrink-0 text-[var(--color-text-muted)]"
      />
      <dd className="m-0">{label}</dd>
    </div>
  );
}
