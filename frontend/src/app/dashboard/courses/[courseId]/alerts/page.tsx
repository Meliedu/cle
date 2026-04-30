"use client";
import { use } from "react";

import { AlertList } from "@/components/decision/alert-list";

export default function AlertsPage(
  props: { readonly params: Promise<{ readonly courseId: string }> },
) {
  const { courseId } = use(props.params);
  return (
    <main className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-[var(--color-text)]">
          Alerts
        </h1>
        <p className="text-sm text-[var(--color-muted)]">
          Auto-evaluated course health signals — dismiss or resolve as you act on each.
        </p>
      </header>
      <AlertList courseId={courseId} />
    </main>
  );
}
