"use client";

import { useLocale, useTranslations } from "next-intl";
import {
  BookOpen,
  CalendarClock,
  ClipboardList,
  FileText,
  MapPin,
  Target,
  Clock,
  type LucideIcon,
} from "lucide-react";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

import type { CourseCalendarEvent } from "./calendar-types";
import { paletteSlot } from "./calendar-types";

/**
 * S020 — event-detail drawer. Opens the tapped calendar event in a modal panel
 * whose body ROUTES by `event.kind`: a meeting shows venue + duration, an
 * assignment shows its kind + weight, and a work_item shows its source badge,
 * required flag, and (for a student) the progress status. Built on the shared
 * base-ui Dialog so Escape / backdrop / focus handling come for free; the
 * open/close animation is suppressed under `prefers-reduced-motion`.
 */

interface EventDetailDrawerProps {
  /** The tagged event to detail, or `null` when the drawer is closed. */
  readonly selected: CourseCalendarEvent | null;
  readonly onClose: () => void;
}

/** Icon that carries a calendar event's identity (decorative). */
function eventIcon(item: CourseCalendarEvent): LucideIcon {
  const { event } = item;
  if (event.kind === "meeting") return CalendarClock;
  if (event.kind === "assignment") return ClipboardList;
  switch (event.source_kind) {
    case "checkpoint":
      return Target;
    case "material":
      return BookOpen;
    default:
      return FileText;
  }
}

export function EventDetailDrawer({ selected, onClose }: EventDetailDrawerProps) {
  const t = useTranslations("patterns.calendar");
  const locale = useLocale();

  const open = selected !== null;

  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop
          className="fixed inset-0 z-50 bg-[oklch(20%_0.01_50/0.28)] duration-[var(--duration-fast)] data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0 motion-reduce:animate-none"
        />
        <DialogPrimitive.Popup
          data-slot="calendar-event-detail"
          className="fixed top-1/2 left-1/2 z-50 w-full max-w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 rounded-[var(--radius-2xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-[var(--shadow-xl)] outline-none duration-[var(--duration-fast)] data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95 motion-reduce:animate-none sm:max-w-md"
        >
          {selected ? (
            <DrawerBody item={selected} locale={locale} t={t} onClose={onClose} />
          ) : null}
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

interface DrawerBodyProps {
  readonly item: CourseCalendarEvent;
  readonly locale: string;
  readonly t: ReturnType<typeof useTranslations>;
  readonly onClose: () => void;
}

function DrawerBody({ item, locale, t, onClose }: DrawerBodyProps) {
  const { event } = item;
  const Icon = eventIcon(item);
  const slot = paletteSlot(item.colorIndex);

  const start = new Date(event.at);
  const when = start.toLocaleString(locale, {
    weekday: "long",
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  });

  const kindLabel =
    event.kind === "work_item"
      ? t(`source.${event.source_kind}`)
      : t(`kind.${event.kind}`);

  return (
    <div className="space-y-5">
      <header className="flex items-start gap-3 pr-8">
        <span
          className={cn(
            "mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-lg)]",
            slot.block
          )}
        >
          <Icon aria-hidden="true" strokeWidth={1.85} className="size-5 text-[var(--color-text)]" />
        </span>
        <div className="min-w-0 space-y-1">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            {kindLabel}
          </span>
          <DialogPrimitive.Title className="text-[17px] font-semibold leading-snug tracking-tight text-[var(--color-text)]">
            {event.title}
          </DialogPrimitive.Title>
        </div>
      </header>

      <dl className="space-y-3 text-[13px]">
        <DetailRow icon={CalendarClock} label={t("drawer.course")}>
          {item.courseCode}
        </DetailRow>
        <DetailRow icon={Clock} label={t("drawer.when")}>
          {when}
        </DetailRow>

        {event.kind === "meeting" ? (
          <>
            {event.location ? (
              <DetailRow icon={MapPin} label={t("drawer.location")}>
                {event.location}
              </DetailRow>
            ) : null}
            {event.duration_minutes ? (
              <DetailRow icon={Clock} label={t("drawer.duration")}>
                {t("drawer.minutes", { count: event.duration_minutes })}
              </DetailRow>
            ) : null}
          </>
        ) : null}

        {event.kind === "assignment" && event.weight !== null ? (
          <DetailRow icon={ClipboardList} label={t("drawer.weight")}>
            {`${event.weight}%`}
          </DetailRow>
        ) : null}

        {event.kind === "work_item" ? (
          <>
            <DetailRow icon={Target} label={t("drawer.requirement")}>
              {event.required ? t("drawer.required") : t("drawer.optional")}
            </DetailRow>
            {event.status ? (
              <DetailRow icon={FileText} label={t("drawer.status")}>
                {t(`status.${event.status}`)}
              </DetailRow>
            ) : null}
          </>
        ) : null}
      </dl>

      <DialogPrimitive.Close
        render={<Button variant="outline" className="w-full" />}
        onClick={onClose}
      >
        {t("drawer.close")}
      </DialogPrimitive.Close>
    </div>
  );
}

interface DetailRowProps {
  readonly icon: LucideIcon;
  readonly label: string;
  readonly children: React.ReactNode;
}

function DetailRow({ icon: Icon, label, children }: DetailRowProps) {
  return (
    <div className="flex items-center gap-3">
      <Icon
        aria-hidden="true"
        strokeWidth={1.75}
        className="size-4 shrink-0 text-[var(--color-text-muted)]"
      />
      <dt className="sr-only">{label}</dt>
      <dd className="min-w-0 flex-1 truncate text-[var(--color-text-secondary)]">
        {children}
      </dd>
    </div>
  );
}
