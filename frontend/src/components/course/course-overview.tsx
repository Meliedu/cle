"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import {
  ArrowRight,
  CalendarClock,
  Check,
  Copy,
  Eye,
  EyeOff,
  FileText,
  KeyRound,
  Users,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StateBanner } from "@/components/patterns";
import { useCourse } from "@/hooks/use-courses";
import { useMeetings } from "@/hooks/use-meetings";
import { useDocuments } from "@/hooks/use-documents";
import { useRoster } from "@/hooks/use-enrollment";
import { isCoursePublished } from "./course-workspace-shell";

interface CourseOverviewProps {
  readonly courseId: string;
}

/** A masked stand-in the same length as the code, until the teacher reveals it. */
function maskCode(code: string): string {
  return "•".repeat(Math.max(code.length, 8));
}

/**
 * T029 — teacher course overview. Reads `useCourse` for state (setup /
 * context status, join code) and layers three counts on top: sessions
 * (`useMeetings`), enrolled students (`useRoster`, role === student), and
 * materials (`useDocuments`). A draft course surfaces a `StateBanner` linking
 * back into setup; the class code reuses the P1 reveal/copy affordance
 * (read-only here — rotate/deactivate stay in the setup class-code step).
 */
export function CourseOverview({ courseId }: CourseOverviewProps) {
  const t = useTranslations("teacher.course.overview");
  const { data: course } = useCourse(courseId);
  const meetings = useMeetings(courseId);
  const roster = useRoster(courseId);
  const documents = useDocuments(courseId);

  if (!course) return null;

  const published = isCoursePublished(course);
  const setupHref = `/teacher/courses/${courseId}/setup`;
  const scheduleHref = `/teacher/courses/${courseId}/schedule`;

  const sessionCount = meetings.data?.length ?? null;
  const studentCount =
    roster.data?.filter((r) => r.role === "student").length ?? null;
  const materialCount = documents.data?.length ?? null;

  return (
    <div className="space-y-6">
      {!published ? (
        <StateBanner
          tone="warning"
          title={t("draftBannerTitle")}
          reason={t("draftBannerReason")}
          action={
            <Button size="sm" variant="outline" render={<Link href={setupHref} />}>
              {t("finishSetup")}
            </Button>
          }
        />
      ) : null}

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          icon={CalendarClock}
          label={t("stats.sessions")}
          value={sessionCount}
          loading={meetings.isLoading}
        />
        <StatCard
          icon={Users}
          label={t("stats.students")}
          value={studentCount}
          loading={roster.isLoading}
        />
        <StatCard
          icon={FileText}
          label={t("stats.materials")}
          value={materialCount}
          loading={documents.isLoading}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <CourseAccessCard
          code={course.enroll_code}
          active={course.enroll_code_active}
          setupHref={setupHref}
        />
        <QuickLinksCard scheduleHref={scheduleHref} setupHref={setupHref} />
      </div>
    </div>
  );
}

interface StatCardProps {
  readonly icon: LucideIcon;
  readonly label: string;
  readonly value: number | null;
  readonly loading: boolean;
}

function StatCard({ icon: Icon, label, value, loading }: StatCardProps) {
  return (
    <div className="flex items-center gap-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary)]">
        <Icon aria-hidden="true" strokeWidth={1.85} className="size-5" />
      </div>
      <div>
        <p className="text-[12px] text-[var(--color-text-muted)]">{label}</p>
        {loading ? (
          <Skeleton className="mt-1 h-7 w-8" />
        ) : (
          <p className="text-[20px] font-bold leading-tight text-[var(--color-text)]">
            {value ?? 0}
          </p>
        )}
      </div>
    </div>
  );
}

interface CourseAccessCardProps {
  readonly code: string;
  readonly active: boolean;
  readonly setupHref: string;
}

function CourseAccessCard({ code, active, setupHref }: CourseAccessCardProps) {
  const t = useTranslations("teacher.course.overview.access");
  const [revealed, setRevealed] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const copyCode = useCallback(async () => {
    setError(null);
    try {
      await navigator.clipboard.writeText(code);
      setRevealed(true);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setError(t("copyError"));
    }
  }, [code, t]);

  return (
    <div className="space-y-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <KeyRound
            aria-hidden="true"
            strokeWidth={1.85}
            className="size-4 text-[var(--color-primary)]"
          />
          <div>
            <p className="text-[14px] font-semibold text-[var(--color-text)]">
              {t("title")}
            </p>
            <p className="text-[12px] text-[var(--color-text-muted)]">
              {t("subtitle")}
            </p>
          </div>
        </div>
        {active ? (
          <Badge variant="secondary">{t("active")}</Badge>
        ) : (
          <Badge variant="outline">{t("inactive")}</Badge>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2.5">
        <code
          aria-label={revealed ? t("codeVisible") : t("codeHidden")}
          className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] px-4 py-2.5 font-mono text-[18px] font-semibold tracking-[0.2em] text-[var(--color-text)]"
        >
          {revealed ? code : maskCode(code)}
        </code>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => setRevealed((v) => !v)}
        >
          {revealed ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
          {revealed ? t("hide") : t("reveal")}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void copyCode()}
        >
          {copied ? (
            <Check aria-hidden="true" className="text-[var(--color-success)]" />
          ) : (
            <Copy aria-hidden="true" />
          )}
          {copied ? t("copied") : t("copy")}
        </Button>
      </div>

      {error ? (
        <p role="alert" className="text-[13px] text-[var(--color-error)]">
          {error}
        </p>
      ) : null}

      <Link
        href={setupHref}
        className="inline-flex items-center gap-1 text-[13px] font-medium text-[var(--color-primary)] hover:underline"
      >
        {t("manage")}
        <ArrowRight aria-hidden="true" className="size-3.5" />
      </Link>
    </div>
  );
}

interface QuickLinksCardProps {
  readonly scheduleHref: string;
  readonly setupHref: string;
}

function QuickLinksCard({ scheduleHref, setupHref }: QuickLinksCardProps) {
  const t = useTranslations("teacher.course.overview.links");
  const links = [
    { href: scheduleHref, label: t("schedule"), icon: CalendarClock },
    { href: setupHref, label: t("setup"), icon: KeyRound },
  ] as const;

  return (
    <div className="space-y-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <p className="text-[14px] font-semibold text-[var(--color-text)]">
        {t("title")}
      </p>
      <ul className="space-y-1.5">
        {links.map(({ href, label, icon: Icon }) => (
          <li key={href}>
            <Link
              href={href}
              className="flex items-center justify-between rounded-[var(--radius-md)] border border-transparent px-3 py-2.5 text-[13px] font-medium text-[var(--color-text)] transition-colors duration-[var(--duration-fast)] hover:border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]"
            >
              <span className="flex items-center gap-2.5">
                <Icon
                  aria-hidden="true"
                  strokeWidth={1.85}
                  className="size-4 text-[var(--color-text-muted)]"
                />
                {label}
              </span>
              <ArrowRight
                aria-hidden="true"
                className="size-4 text-[var(--color-text-muted)]"
              />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
