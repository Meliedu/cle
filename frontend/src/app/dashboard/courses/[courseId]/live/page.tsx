"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRole } from "@/hooks/use-role";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Radio,
  Plus,
  Users,
  Clock,
  ArrowLeft,
  Zap,
} from "lucide-react";
import {
  useLiveSessions,
  useCreateLiveSession,
} from "@/hooks/use-live-quiz";
import { useQuizzes } from "@/hooks/use-quizzes";
import { formatRelativeTime } from "@/lib/format";

interface LiveSessionListPageProps {
  params: Promise<{ courseId: string }>;
}

export default function LiveSessionListPage({
  params,
}: LiveSessionListPageProps) {
  const { courseId } = use(params);
  const router = useRouter();
  const { isInstructor, isLoaded: userLoaded } = useRole();
  const { data: sessions, isLoading: sessionsLoading } =
    useLiveSessions(courseId);
  const { data: quizzes, isLoading: quizzesLoading } = useQuizzes(courseId);
  const createSession = useCreateLiveSession(courseId);

  const [createOpen, setCreateOpen] = useState(false);
  const [selectedQuizId, setSelectedQuizId] = useState("");
  const [timeLimit, setTimeLimit] = useState("30");
  const [joinCodeInput, setJoinCodeInput] = useState("");

  const handleCreate = () => {
    if (!selectedQuizId) return;
    createSession.mutate(
      {
        quiz_id: selectedQuizId,
        time_limit_seconds: parseInt(timeLimit, 10) || 30,
      },
      {
        onSuccess: (session) => {
          setCreateOpen(false);
          router.push(
            `/dashboard/courses/${courseId}/live/${session.id}`
          );
        },
      }
    );
  };

  const publishedQuizzes = quizzes?.filter((q) => q.is_published);

  if (!userLoaded) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="space-y-3">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-[var(--radius-lg)]" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
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
        {isInstructor && (
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="size-4" />
            Create Session
          </Button>
        )}
      </div>

      {/* Join by code (students) */}
      {!isInstructor && (
        <Card>
          <CardContent className="flex items-center gap-3">
            <Input
              placeholder="Enter join code..."
              value={joinCodeInput}
              onChange={(e) =>
                setJoinCodeInput(e.target.value.toUpperCase())
              }
              maxLength={6}
              className="font-mono text-lg tracking-widest uppercase"
            />
            <Button
              disabled={joinCodeInput.length < 6}
              onClick={() => {
                /* Join code lookup would go here — for now navigate */
              }}
            >
              <Zap className="size-4" />
              Join
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Active sessions */}
      <section className="space-y-3">
        <h2 className="text-sm font-medium text-[var(--color-text-muted)]">
          Active Sessions
        </h2>

        {sessionsLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 2 }).map((_, i) => (
              <Skeleton key={i} className="h-20 rounded-[var(--radius-lg)]" />
            ))}
          </div>
        ) : sessions && sessions.length > 0 ? (
          <div className="space-y-3">
            {sessions.map((session) => (
              <Link
                key={session.id}
                href={`/dashboard/courses/${courseId}/live/${session.id}`}
              >
                <Card className="transition-all duration-[var(--duration-fast)] hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-md)]">
                  <CardContent className="flex items-center gap-4">
                    <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-[var(--color-success-light)]">
                      <Radio className="size-5 text-[var(--color-success)]" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm font-bold text-[var(--color-text)]">
                          {session.join_code}
                        </span>
                        <Badge
                          variant="outline"
                          className="border-[var(--color-success)] text-[var(--color-success)]"
                        >
                          {session.status}
                        </Badge>
                      </div>
                      <div className="mt-0.5 flex items-center gap-3 text-xs text-[var(--color-text-muted)]">
                        <span className="flex items-center gap-1">
                          <Users className="size-3" />
                          {session.participant_count} participants
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock className="size-3" />
                          {formatRelativeTime(session.created_at)}
                        </span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="flex flex-col items-center py-12 text-center">
              <div className="mb-4 flex size-12 items-center justify-center rounded-full bg-[var(--color-primary-light)]">
                <Radio className="size-6 text-[var(--color-primary)]" />
              </div>
              <h3 className="font-semibold text-[var(--color-text)]">
                No active sessions
              </h3>
              <p className="mt-1 max-w-sm text-sm text-[var(--color-text-muted)]">
                {isInstructor
                  ? "Create a live quiz session to engage your students in real-time."
                  : "There are no active live sessions right now. Check back later or enter a join code."}
              </p>
            </CardContent>
          </Card>
        )}
      </section>

      {/* Create session dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Live Session</DialogTitle>
            <DialogDescription>
              Choose a published quiz and configure the session settings.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-[var(--color-text)]">
                Quiz
              </label>
              {quizzesLoading ? (
                <Skeleton className="h-8 w-full" />
              ) : publishedQuizzes && publishedQuizzes.length > 0 ? (
                <div className="space-y-2">
                  {publishedQuizzes.map((quiz) => (
                    <button
                      key={quiz.id}
                      onClick={() => setSelectedQuizId(quiz.id)}
                      className={`w-full rounded-[var(--radius-md)] border px-3 py-2 text-left text-sm transition-colors ${
                        selectedQuizId === quiz.id
                          ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]"
                          : "border-[var(--color-border)] hover:border-[var(--color-border-hover)]"
                      }`}
                    >
                      <span className="font-medium text-[var(--color-text)]">
                        {quiz.title}
                      </span>
                      <span className="ml-2 text-xs text-[var(--color-text-muted)]">
                        {quiz.question_count} questions
                      </span>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-[var(--color-text-muted)]">
                  No published quizzes available. Publish a quiz first.
                </p>
              )}
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-[var(--color-text)]">
                Time limit per question (seconds)
              </label>
              <Input
                type="number"
                min="10"
                max="120"
                value={timeLimit}
                onChange={(e) => setTimeLimit(e.target.value)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              disabled={!selectedQuizId || createSession.isPending}
            >
              {createSession.isPending ? "Creating..." : "Create & Start"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
