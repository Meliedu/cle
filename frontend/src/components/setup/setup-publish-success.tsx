"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import {
  ArrowUpRight,
  CalendarDays,
  FolderOpen,
  KeyRound,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { StateBanner } from "@/components/patterns";
import { cn } from "@/lib/utils";
import { useCourse } from "@/hooks/use-courses";

interface SetupPublishSuccessProps {
  readonly courseId: string;
  /** Jump back to the class-code step so the teacher can reveal/share the code. */
  readonly onShowCode?: () => void;
}

/** Two-letter initials for the course avatar (falls back to "C"). */
function courseInitials(name: string): string {
  const letters = name
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => word[0]?.toUpperCase() ?? "")
    .join("");
  return letters.slice(0, 2) || name.slice(0, 2).toUpperCase() || "C";
}

/**
 * T027 — setup-publish-success. The terminal confirmation shown once
 * `usePublishSetup` succeeds (`setup_status==='published'`,
 * `context_status==='approved'`, Decision 1): the course is now open, so this
 * celebrates and points the teacher at the immediate next actions — share the
 * class code, open the course, or check the calendar. `StateBanner tone="success"`.
 */
export function SetupPublishSuccess({ courseId, onShowCode }: SetupPublishSuccessProps) {
  const t = useTranslations("teacher.setup.publishSuccess");
  const { data: course } = useCourse(courseId);

  const name = course?.name ?? "";
  const description = course?.description ?? "";
  const semester = course?.semester ?? "";

  return (
    <div className="space-y-6">
      <div className="space-y-1.5 text-center">
        <h2 className="text-[20px] font-semibold tracking-tight text-[var(--color-text)]">
          {t("title")}
        </h2>
        <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {name ? t("subtitle", { name }) : t("tagline")}
        </p>
      </div>

      <StateBanner tone="success" title={t("title")} reason={t("tagline")} />

      <div className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <div className="flex items-center gap-4">
          <span
            aria-hidden="true"
            className="flex size-12 shrink-0 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--color-primary-light)] text-[16px] font-semibold text-[var(--color-primary-hover)]"
          >
            {courseInitials(name)}
          </span>
          <div className="min-w-0 flex-1 space-y-0.5">
            <div className="flex flex-wrap items-center gap-2">
              <p className="truncate text-[15px] font-semibold text-[var(--color-text)]">
                {name}
              </p>
              <Badge variant="secondary">{t("publishedBadge")}</Badge>
            </div>
            {description ? (
              <p className="truncate text-[13px] text-[var(--color-text-secondary)]">
                {description}
              </p>
            ) : null}
            {semester ? (
              <p className="text-[12px] text-[var(--color-text-muted)]">{semester}</p>
            ) : null}
          </div>
        </div>

        <div className="mt-5 border-t border-[var(--color-border)] pt-5">
          <p className="text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            {t("whatsNext")}
          </p>
          <div className="mt-3 grid gap-2.5 sm:grid-cols-3">
            {/*
              The teacher course-detail workspace ships in P4; until then link to
              the course list (which exists and now shows the published course)
              rather than `/teacher/courses/{id}`, which has no page and 404s.
            */}
            <NextActionLink
              href="/teacher/courses"
              icon={FolderOpen}
              title={t("openCourse")}
              hint={t("openCourseHint")}
            />
            <NextActionButton
              icon={KeyRound}
              title={t("showCode")}
              hint={t("showCodeHint")}
              onClick={onShowCode}
            />
            <NextActionLink
              href="/teacher/calendar"
              icon={CalendarDays}
              title={t("viewCalendar")}
              hint={t("viewCalendarHint")}
            />
          </div>
        </div>
      </div>

      <p className="text-center text-[12px] leading-relaxed text-[var(--color-text-muted)]">
        {t("footnote")}
      </p>
    </div>
  );
}

const TILE_CLASS =
  "group flex h-full flex-col gap-1.5 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] p-3.5 text-left transition-colors hover:border-[var(--color-primary)]/40 hover:bg-[var(--color-primary-light)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]";

interface NextActionProps {
  readonly icon: LucideIcon;
  readonly title: string;
  readonly hint: string;
}

function TileInner({ icon: Icon, title, hint }: NextActionProps) {
  return (
    <>
      <span className="flex items-center justify-between">
        <Icon
          aria-hidden="true"
          strokeWidth={1.85}
          className="size-4.5 text-[var(--color-primary-hover)]"
        />
        <ArrowUpRight
          aria-hidden="true"
          className="size-4 text-[var(--color-text-muted)] transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
        />
      </span>
      <span className="text-[13px] font-semibold text-[var(--color-text)]">{title}</span>
      <span className="text-[12px] leading-snug text-[var(--color-text-secondary)]">
        {hint}
      </span>
    </>
  );
}

function NextActionLink({
  href,
  ...rest
}: NextActionProps & { readonly href: string }) {
  return (
    <Link href={href} className={cn(TILE_CLASS)}>
      <TileInner {...rest} />
    </Link>
  );
}

function NextActionButton({
  onClick,
  ...rest
}: NextActionProps & { readonly onClick?: () => void }) {
  return (
    <button type="button" onClick={onClick} className={cn(TILE_CLASS)}>
      <TileInner {...rest} />
    </button>
  );
}
