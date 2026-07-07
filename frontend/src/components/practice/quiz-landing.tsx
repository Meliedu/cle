"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Award, CalendarClock, Clock, ListChecks, Tag } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader, StateBanner } from "@/components/patterns";
import type { QuizDetailResponse, LateRule } from "@/hooks/use-quizzes";

interface QuizLandingProps {
  readonly quiz: QuizDetailResponse;
  readonly courseId: string;
  readonly questionCount: number;
  /** Resolved best-effort by the runner from the student's score record. */
  readonly categoryName: string | null;
  readonly onStart: () => void;
}

function formatDateTime(iso: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

/**
 * Student graded-quiz landing (F8 / S050). Surfaces the score-bearing disclosure
 * BEFORE start — points, category, late rule, due/close — straight from the
 * `QuizDetailResponse` publish-settings fields (B6 read). `correct_answer` stays
 * redacted; nothing here reveals answers. The student must read the stakes, then
 * explicitly start the attempt.
 */
export function QuizLanding({
  quiz,
  courseId,
  questionCount,
  categoryName,
  onStart,
}: QuizLandingProps) {
  const t = useTranslations("student.quiz");
  const backHref = `/student/courses/${courseId}/activities`;

  const lateRuleLabel = (rule: LateRule | null): string => {
    switch (rule) {
      case "accept_late":
        return t("landing.lateAccept");
      case "reject_late":
        return t("landing.lateReject");
      case "accept_with_flag":
        return t("landing.lateFlag");
      default:
        return t("landing.notSet");
    }
  };

  const rows: ReadonlyArray<{
    readonly key: string;
    readonly Icon: LucideIcon;
    readonly label: string;
    readonly value: string;
  }> = [
    {
      key: "points",
      Icon: Award,
      label: t("landing.points"),
      value: quiz.points != null ? String(quiz.points) : t("landing.notSet"),
    },
    {
      key: "category",
      Icon: Tag,
      label: t("landing.category"),
      value: categoryName ?? t("landing.notSet"),
    },
    {
      key: "late",
      Icon: Clock,
      label: t("landing.lateRule"),
      value: lateRuleLabel(quiz.late_rule),
    },
    {
      key: "due",
      Icon: CalendarClock,
      label: t("landing.dueAt"),
      value: formatDateTime(quiz.due_at) ?? t("landing.notSet"),
    },
    {
      key: "close",
      Icon: CalendarClock,
      label: t("landing.closeAt"),
      value: formatDateTime(quiz.close_at) ?? t("landing.notSet"),
    },
  ];

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <PageHeader
        title={quiz.title}
        description={quiz.description ?? undefined}
        breadcrumb={
          <Link href={backHref} className="hover:text-[var(--color-text)]">
            {t("load.back")}
          </Link>
        }
      />

      <StateBanner
        tone="info"
        title={
          quiz.score_bearing
            ? t("landing.scoreBearingTitle")
            : t("landing.notGradedTitle")
        }
        reason={
          quiz.score_bearing
            ? t("landing.scoreBearingReason")
            : t("landing.notGradedReason")
        }
      />

      {quiz.score_bearing ? (
        <Card>
          <CardContent className="space-y-3 py-5">
            <p className="text-[13px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              {t("landing.detailsTitle")}
            </p>
            <dl className="divide-y divide-[var(--color-border)]/70">
              {rows.map(({ key, Icon, label, value }) => (
                <div
                  key={key}
                  className="flex items-center justify-between gap-4 py-2.5"
                >
                  <dt className="flex items-center gap-2 text-[13px] text-[var(--color-text-secondary)]">
                    <Icon
                      aria-hidden="true"
                      className="size-4 text-[var(--color-text-muted)]"
                    />
                    {label}
                  </dt>
                  <dd className="text-right text-sm font-medium text-[var(--color-text)]">
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
          </CardContent>
        </Card>
      ) : null}

      <div className="flex items-center gap-2 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-[13px] text-[var(--color-text-secondary)]">
        <ListChecks
          aria-hidden="true"
          className="size-4 text-[var(--color-text-muted)]"
        />
        {t("landing.questionCount", { count: questionCount })}
      </div>

      <Button
        className="w-full sm:w-auto"
        disabled={questionCount === 0}
        onClick={onStart}
      >
        {t("landing.start")}
      </Button>

      {questionCount === 0 ? (
        <StateBanner
          tone="waiting"
          title={t("landing.emptyTitle")}
          reason={t("landing.emptyReason")}
        />
      ) : null}
    </div>
  );
}
