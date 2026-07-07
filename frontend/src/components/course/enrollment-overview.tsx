"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import {
  ArrowRight,
  CircleCheck,
  CircleSlash,
  ClipboardCheck,
  UserPlus,
  Users,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StateBanner } from "@/components/patterns";
import { useCourse } from "@/hooks/use-courses";
import { useJoinRequests, useRoster } from "@/hooks/use-enrollment";

interface EnrollmentOverviewProps {
  readonly courseId: string;
}

/**
 * T031 — teacher enrollment overview. Summarises the enrollment state of a
 * course: active student count (`useRoster`, role === student), pending
 * join-request count (`useJoinRequests`, read-only here), the course
 * `join_mode`, and whether the class code is currently accepting joins. When
 * there are pending requests a `StateBanner` nudges the teacher to the
 * approval screen (Task 15). This is the read-only VIEW — the approve/deny
 * mutations live with the T033 join-request-approval screen (Task 15); this
 * screen only links into it.
 */
export function EnrollmentOverview({ courseId }: EnrollmentOverviewProps) {
  const t = useTranslations("teacher.enrollment");
  const { data: course } = useCourse(courseId);
  const roster = useRoster(courseId);
  const joinRequests = useJoinRequests(courseId);

  const studentCount =
    roster.data?.filter((r) => r.role === "student").length ?? null;
  const pendingCount = joinRequests.data?.length ?? null;

  // The enrollment page hosts overview + roster (this task) and the
  // join-request approval section (Task 15) as anchored sections on one page.
  const rosterHref = "#roster";
  const requestsHref = "#requests";

  const codeActive = course?.enroll_code_active ?? false;
  const requiresApproval = course?.join_mode === "code_plus_approval";

  return (
    <section className="space-y-6">
      <div className="space-y-1">
        <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
          {t("title")}
        </h2>
        <p className="text-[13px] text-[var(--color-text-secondary)]">
          {t("subtitle")}
        </p>
      </div>

      {pendingCount && pendingCount > 0 ? (
        <StateBanner
          tone="waiting"
          title={t("pendingBanner.title", { count: pendingCount })}
          reason={t("pendingBanner.reason")}
          action={
            <Button size="sm" variant="outline" render={<Link href={requestsHref} />}>
              {t("pendingBanner.review")}
            </Button>
          }
        />
      ) : null}

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          icon={Users}
          label={t("stats.students")}
          value={studentCount}
          loading={roster.isLoading}
        />
        <StatCard
          icon={ClipboardCheck}
          label={t("stats.pending")}
          value={pendingCount}
          loading={joinRequests.isLoading}
          hint={t("stats.pendingHint")}
        />
        <JoinAccessCard active={codeActive} requiresApproval={requiresApproval} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <NavCard
          icon={Users}
          title={t("links.roster.title")}
          description={t("links.roster.description")}
          href={rosterHref}
          cta={t("links.roster.cta")}
        />
        <NavCard
          icon={UserPlus}
          title={t("links.requests.title")}
          description={t("links.requests.description")}
          href={requestsHref}
          cta={t("links.requests.cta")}
        />
      </div>
    </section>
  );
}

interface StatCardProps {
  readonly icon: LucideIcon;
  readonly label: string;
  readonly value: number | null;
  readonly loading: boolean;
  readonly hint?: string;
}

function StatCard({ icon: Icon, label, value, loading, hint }: StatCardProps) {
  return (
    <div className="flex items-start gap-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary)]">
        <Icon aria-hidden="true" strokeWidth={1.85} className="size-5" />
      </div>
      <div className="min-w-0">
        <p className="text-[12px] text-[var(--color-text-muted)]">{label}</p>
        {loading ? (
          <Skeleton className="mt-1 h-7 w-8" />
        ) : (
          <p className="text-[20px] font-bold leading-tight text-[var(--color-text)]">
            {value ?? 0}
          </p>
        )}
        {hint ? (
          <p className="mt-0.5 text-[11px] text-[var(--color-text-muted)]">
            {hint}
          </p>
        ) : null}
      </div>
    </div>
  );
}

interface JoinAccessCardProps {
  readonly active: boolean;
  readonly requiresApproval: boolean;
}

function JoinAccessCard({ active, requiresApproval }: JoinAccessCardProps) {
  const t = useTranslations("teacher.enrollment");
  const Icon = active ? CircleCheck : CircleSlash;
  return (
    <div className="flex items-start gap-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div
        className="flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-md)]"
        style={{
          background: active
            ? "var(--color-success-light, var(--color-primary-light))"
            : "var(--color-surface-hover)",
        }}
      >
        <Icon
          aria-hidden="true"
          strokeWidth={1.85}
          className={
            active
              ? "size-5 text-[var(--color-success)]"
              : "size-5 text-[var(--color-text-muted)]"
          }
        />
      </div>
      <div className="min-w-0">
        <p className="text-[12px] text-[var(--color-text-muted)]">
          {t("stats.access")}
        </p>
        <p className="mt-0.5 flex items-center gap-2 text-[15px] font-semibold text-[var(--color-text)]">
          {active ? t("access.active") : t("access.inactive")}
          {requiresApproval ? (
            <Badge variant="outline" className="text-[10px]">
              {t("access.approval")}
            </Badge>
          ) : null}
        </p>
        <p className="mt-0.5 text-[11px] text-[var(--color-text-muted)]">
          {requiresApproval ? t("access.approvalHint") : t("access.codeHint")}
        </p>
      </div>
    </div>
  );
}

interface NavCardProps {
  readonly icon: LucideIcon;
  readonly title: string;
  readonly description: string;
  readonly href: string;
  readonly cta: string;
}

function NavCard({ icon: Icon, title, description, href, cta }: NavCardProps) {
  return (
    <div className="space-y-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <div className="flex items-center gap-2.5">
        <Icon
          aria-hidden="true"
          strokeWidth={1.85}
          className="size-4 text-[var(--color-primary)]"
        />
        <p className="text-[14px] font-semibold text-[var(--color-text)]">
          {title}
        </p>
      </div>
      <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
        {description}
      </p>
      <Link
        href={href}
        className="inline-flex items-center gap-1 text-[13px] font-medium text-[var(--color-primary)] hover:underline"
      >
        {cta}
        <ArrowRight aria-hidden="true" className="size-3.5" />
      </Link>
    </div>
  );
}
