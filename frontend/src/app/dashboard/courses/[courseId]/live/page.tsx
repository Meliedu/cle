"use client";

import { use } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { LiveSessionsPanel } from "@/components/live-quiz/live-sessions-panel";

interface LiveSessionListPageProps {
  params: Promise<{ courseId: string }>;
}

export default function LiveSessionListPage({
  params,
}: LiveSessionListPageProps) {
  const { courseId } = use(params);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center gap-3">
        <Link href={`/dashboard/courses/${courseId}`}>
          <Button variant="ghost" size="sm">
            <ArrowLeft className="size-4" />
            Back
          </Button>
        </Link>
        <h1 className="text-xl font-bold text-[var(--color-text)]">
          Live Quiz
        </h1>
      </div>
      <LiveSessionsPanel courseId={courseId} />
    </div>
  );
}
