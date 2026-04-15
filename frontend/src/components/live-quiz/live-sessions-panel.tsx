"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRole } from "@/hooks/use-role";
import { Button } from "@/components/ui/button";
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
  Zap,
  Trash2,
} from "lucide-react";
import {
  useLiveSessions,
  useCreateLiveSession,
  useDeleteLiveSession,
  useFindLiveSessionByCode,
} from "@/hooks/use-live-quiz";
import { useQuizzes, useDeleteQuiz } from "@/hooks/use-quizzes";
import {
  useQuizFolders,
  useCreateQuizFolder,
  useRenameQuizFolder,
  useDeleteQuizFolder,
  useMoveQuizFolder,
  useMoveQuizToFolder,
} from "@/hooks/use-quiz-folders";
import { formatRelativeTime } from "@/lib/format";
import { GenerateLiveQuizDialog } from "@/components/live-quiz/generate-live-quiz-dialog";
import { ImportFromQuizDialog } from "@/components/live-quiz/import-from-quiz-dialog";
import { QuizBankBrowser } from "@/components/live-quiz/quiz-bank-browser";
import { QuizFolderPicker } from "@/components/live-quiz/quiz-folder-picker";

interface LiveSessionsPanelProps {
  readonly courseId: string;
}

export function LiveSessionsPanel({ courseId }: LiveSessionsPanelProps) {
  const router = useRouter();
  const { isInstructor } = useRole();
  const { data: sessions, isLoading: sessionsLoading } =
    useLiveSessions(courseId);
  const { data: liveQuizzes, isLoading: quizzesLoading } = useQuizzes(
    courseId,
    "live"
  );
  const createSession = useCreateLiveSession(courseId);
  const deleteSession = useDeleteLiveSession(courseId);
  const deleteQuiz = useDeleteQuiz(courseId);
  const findByCode = useFindLiveSessionByCode();
  const { data: folders } = useQuizFolders(courseId, "live");
  const createFolder = useCreateQuizFolder(courseId);
  const renameFolder = useRenameQuizFolder(courseId);
  const deleteFolder = useDeleteQuizFolder(courseId);
  const moveFolder = useMoveQuizFolder(courseId);
  const moveQuiz = useMoveQuizToFolder(courseId);

  const [createOpen, setCreateOpen] = useState(false);
  const [selectedQuizId, setSelectedQuizId] = useState("");
  const [timeLimit, setTimeLimit] = useState("30");
  const [reviewMode, setReviewMode] = useState<"per_question" | "final">(
    "per_question"
  );
  const [joinCodeInput, setJoinCodeInput] = useState("");
  const [joinError, setJoinError] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [deleteQuizConfirmId, setDeleteQuizConfirmId] = useState<string | null>(
    null
  );

  const handleCreate = () => {
    if (!selectedQuizId) return;
    createSession.mutate(
      {
        quiz_id: selectedQuizId,
        time_limit_seconds: parseInt(timeLimit, 10) || 30,
        settings: { review_mode: reviewMode },
      },
      {
        onSuccess: (session) => {
          setCreateOpen(false);
          router.push(`/dashboard/courses/${courseId}/live/${session.id}`);
        },
      }
    );
  };

  const handleJoinByCode = () => {
    setJoinError(null);
    if (joinCodeInput.length < 6) return;
    findByCode.mutate(joinCodeInput, {
      onSuccess: (session) => {
        router.push(
          `/dashboard/courses/${session.course_id}/live/${session.id}`
        );
      },
      onError: () => {
        setJoinError("No active session found for this code.");
      },
    });
  };

  const handleDelete = (sessionId: string) => {
    deleteSession.mutate(sessionId, {
      onSuccess: () => setDeleteConfirmId(null),
    });
  };

  const publishedQuizzes = liveQuizzes?.filter((q) => q.is_published);

  const hasSessions = !!sessions && sessions.length > 0;

  const sessionsSection = (
    <div className="space-y-3">
      {isInstructor && (
        <Button
          className="w-full"
          size="sm"
          onClick={() => setCreateOpen(true)}
        >
          <Plus className="size-4" />
          Create Session
        </Button>
      )}

      {/* Join by code — compact, no card chrome */}
      <div className="flex flex-col gap-1">
        <div className="flex items-stretch gap-2">
          <Input
            placeholder="Join code"
            value={joinCodeInput}
            onChange={(e) => {
              setJoinCodeInput(e.target.value.toUpperCase());
              setJoinError(null);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleJoinByCode();
            }}
            maxLength={6}
            className="h-9 font-mono text-sm tracking-[0.2em] uppercase"
          />
          <Button
            size="sm"
            disabled={joinCodeInput.length < 6 || findByCode.isPending}
            onClick={handleJoinByCode}
          >
            <Zap className="size-4" />
            Join
          </Button>
        </div>
        {joinError && (
          <p className="text-xs text-[var(--color-error)]">{joinError}</p>
        )}
      </div>

      {/* Active sessions — only rendered when present (no empty state jitter) */}
      {sessionsLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-14 rounded-[var(--radius-md)]" />
          ))}
        </div>
      ) : hasSessions ? (
        <section className="space-y-2">
          <h2 className="px-1 text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
            Active · {sessions!.length}
          </h2>
          <div className="space-y-1.5">
            {sessions!.map((session) => (
              <div
                key={session.id}
                className="group flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-2 transition-colors hover:border-[var(--color-border-hover)]"
              >
                <Link
                  href={`/dashboard/courses/${courseId}/live/${session.id}`}
                  className="flex min-w-0 flex-1 items-center gap-2"
                >
                  <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-success-light)]">
                    <Radio className="size-3.5 text-[var(--color-success)]" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-sm font-bold text-[var(--color-text)]">
                        {session.join_code}
                      </span>
                      <span className="text-[11px] text-[var(--color-success)]">
                        · {session.status}
                      </span>
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 text-[11px] text-[var(--color-text-muted)]">
                      <span className="flex items-center gap-0.5">
                        <Users className="size-3" />
                        {session.participant_count}
                      </span>
                      <span className="flex items-center gap-0.5">
                        <Clock className="size-3" />
                        {formatRelativeTime(session.created_at)}
                      </span>
                    </div>
                  </div>
                </Link>
                {isInstructor && session.is_host && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="size-7 shrink-0 p-0 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
                    onClick={(e) => {
                      e.preventDefault();
                      setDeleteConfirmId(session.id);
                    }}
                    aria-label="Delete session"
                  >
                    <Trash2 className="size-3.5 text-[var(--color-error)]" />
                  </Button>
                )}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {/* Empty state only when there genuinely are no sessions — compact */}
      {!sessionsLoading && !hasSessions && (
        <p className="rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] px-3 py-4 text-center text-xs text-[var(--color-text-muted)]">
          {isInstructor
            ? "No active sessions. Pick a quiz from the bank to start one."
            : "No active sessions right now."}
        </p>
      )}
    </div>
  );

  const bankSection = isInstructor ? (
    <div className="space-y-3">
      {quizzesLoading ? (
        <Skeleton className="h-32 rounded-[var(--radius-lg)]" />
      ) : (
        <QuizBankBrowser
          folders={folders ?? []}
          quizzes={liveQuizzes ?? []}
          onCreateFolder={(parentId, name) =>
            createFolder.mutate({ name, parent_id: parentId, purpose: "live" })
          }
          onRenameFolder={(id, name) =>
            renameFolder.mutate({ folder_id: id, name })
          }
          onDeleteFolder={(id) => deleteFolder.mutate(id)}
          onMoveFolder={(id, parentId) =>
            moveFolder.mutate({ folder_id: id, parent_id: parentId })
          }
          onMoveQuiz={(quizId, folderId) =>
            moveQuiz.mutate({ quiz_id: quizId, folder_id: folderId })
          }
          onStartSession={(quizId) => {
            setSelectedQuizId(quizId);
            setCreateOpen(true);
          }}
          onDeleteQuiz={(quizId) => setDeleteQuizConfirmId(quizId)}
          onGenerate={() => setGenerateOpen(true)}
          onImport={() => setImportOpen(true)}
        />
      )}
    </div>
  ) : null;

  return (
    <div className="space-y-6">
      <div className="grid gap-6 md:grid-cols-5">
        <div className={bankSection ? "md:col-span-2" : "md:col-span-5"}>
          {sessionsSection}
        </div>
        {bankSection && (
          <div className="md:col-span-3">{bankSection}</div>
        )}
      </div>

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
                <Skeleton className="h-40 w-full" />
              ) : publishedQuizzes && publishedQuizzes.length > 0 ? (
                <QuizFolderPicker
                  folders={folders ?? []}
                  quizzes={publishedQuizzes}
                  selectedQuizId={selectedQuizId || null}
                  onSelectQuiz={setSelectedQuizId}
                />
              ) : (
                <p className="text-sm text-[var(--color-text-muted)]">
                  No live quizzes yet. Generate or import one from the question
                  bank above first.
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

            <div className="space-y-2">
              <label className="text-sm font-medium text-[var(--color-text)]">
                Review mode
              </label>
              <div className="grid grid-cols-1 gap-2">
                {(
                  [
                    {
                      value: "per_question",
                      title: "Review after each question",
                      desc: "Students see the correct answer before moving on.",
                    },
                    {
                      value: "final",
                      title: "Review at the end",
                      desc: "Auto-advance to the next question when time is up; show all answers at the end.",
                    },
                  ] as const
                ).map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setReviewMode(opt.value)}
                    className={`rounded-[var(--radius-md)] border px-3 py-2 text-left text-sm transition-colors ${
                      reviewMode === opt.value
                        ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]"
                        : "border-[var(--color-border)] hover:border-[var(--color-border-hover)]"
                    }`}
                  >
                    <span className="font-medium text-[var(--color-text)]">
                      {opt.title}
                    </span>
                    <span className="mt-0.5 block text-xs text-[var(--color-text-muted)]">
                      {opt.desc}
                    </span>
                  </button>
                ))}
              </div>
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

      {/* Delete confirmation dialog */}
      <Dialog
        open={deleteConfirmId !== null}
        onOpenChange={(open) => !open && setDeleteConfirmId(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete live session?</DialogTitle>
            <DialogDescription>
              This will end the session for all participants and remove it
              permanently. Past attempts and quiz content are kept.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteConfirmId(null)}
              disabled={deleteSession.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() =>
                deleteConfirmId && handleDelete(deleteConfirmId)
              }
              disabled={deleteSession.isPending}
            >
              {deleteSession.isPending ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={deleteQuizConfirmId !== null}
        onOpenChange={(open) => !open && setDeleteQuizConfirmId(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete live quiz?</DialogTitle>
            <DialogDescription>
              This removes the quiz and all its questions from the live question
              bank. Any sessions already using it will end. After-class quizzes
              are unaffected.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteQuizConfirmId(null)}
              disabled={deleteQuiz.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={deleteQuiz.isPending}
              onClick={() => {
                if (!deleteQuizConfirmId) return;
                deleteQuiz.mutate(deleteQuizConfirmId, {
                  onSuccess: () => setDeleteQuizConfirmId(null),
                });
              }}
            >
              {deleteQuiz.isPending ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <GenerateLiveQuizDialog
        courseId={courseId}
        open={generateOpen}
        onOpenChange={setGenerateOpen}
      />
      <ImportFromQuizDialog
        courseId={courseId}
        open={importOpen}
        onOpenChange={setImportOpen}
      />
    </div>
  );
}
