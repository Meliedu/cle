"use client";

import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const DIFFICULTIES = ["easy", "medium", "hard"] as const;

interface QuestionLike {
  readonly question_text: string;
  readonly options: Record<string, string> | null;
  readonly correct_answer: string;
  readonly explanation: string | null;
  readonly difficulty: string;
}

interface QuizQuestionEditorProps {
  readonly open: boolean;
  readonly initial: QuestionLike;
  readonly isSaving: boolean;
  readonly onCancel: () => void;
  readonly onSubmit: (patch: {
    question_text: string;
    options: Record<string, string>;
    correct_answer: string;
    explanation: string | null;
    difficulty: string;
  }) => void;
}

export function QuizQuestionEditor({
  open,
  initial,
  isSaving,
  onCancel,
  onSubmit,
}: QuizQuestionEditorProps) {
  const [questionText, setQuestionText] = useState("");
  const [options, setOptions] = useState<Record<string, string>>({});
  const [orderedKeys, setOrderedKeys] = useState<readonly string[]>([]);
  const [correctAnswer, setCorrectAnswer] = useState("");
  const [explanation, setExplanation] = useState("");
  const [difficulty, setDifficulty] = useState("medium");

  useEffect(() => {
    if (!open) return;
    const opts = initial.options ?? {};
    const keys = Object.keys(opts);
    setQuestionText(initial.question_text);
    setOptions(opts);
    setOrderedKeys(keys);
    setCorrectAnswer(
      keys.includes(initial.correct_answer)
        ? initial.correct_answer
        : keys[0] ?? ""
    );
    setExplanation(initial.explanation ?? "");
    setDifficulty(
      (DIFFICULTIES as readonly string[]).includes(initial.difficulty)
        ? initial.difficulty
        : "medium"
    );
  }, [open, initial]);

  const text = questionText.trim();
  const allOptionsFilled = orderedKeys.every(
    (k) => (options[k] ?? "").trim().length > 0
  );
  const canSubmit =
    text.length > 0 &&
    correctAnswer &&
    orderedKeys.includes(correctAnswer) &&
    allOptionsFilled &&
    !isSaving;

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) onCancel();
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Edit Question</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="qq-text">
              Question <span className="text-[var(--color-error)]">*</span>
            </Label>
            <Textarea
              id="qq-text"
              value={questionText}
              onChange={(e) => setQuestionText(e.target.value)}
              rows={3}
              disabled={isSaving}
            />
          </div>

          <div className="space-y-2">
            <Label>Options</Label>
            {orderedKeys.map((key) => (
              <div key={key} className="flex items-start gap-2">
                <span className="mt-2 w-6 shrink-0 text-xs font-bold uppercase text-[var(--color-text-muted)]">
                  {key}
                </span>
                <Input
                  value={options[key] ?? ""}
                  onChange={(e) =>
                    setOptions((o) => ({ ...o, [key]: e.target.value }))
                  }
                  disabled={isSaving}
                />
              </div>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Correct answer</Label>
              <Select
                value={correctAnswer}
                onValueChange={(v) => setCorrectAnswer(v ?? correctAnswer)}
                disabled={isSaving}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {orderedKeys.map((k) => (
                    <SelectItem key={k} value={k}>
                      {k}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>Difficulty</Label>
              <Select
                value={difficulty}
                onValueChange={(v) => setDifficulty(v ?? "medium")}
                disabled={isSaving}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DIFFICULTIES.map((d) => (
                    <SelectItem key={d} value={d}>
                      <span className="capitalize">{d}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="qq-explanation">Explanation (optional)</Label>
            <Textarea
              id="qq-explanation"
              value={explanation}
              onChange={(e) => setExplanation(e.target.value)}
              rows={2}
              disabled={isSaving}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={onCancel}
            disabled={isSaving}
          >
            Cancel
          </Button>
          <Button
            type="button"
            disabled={!canSubmit}
            onClick={() =>
              onSubmit({
                question_text: text,
                options: Object.fromEntries(
                  orderedKeys.map((k) => [k, (options[k] ?? "").trim()])
                ),
                correct_answer: correctAnswer,
                explanation: explanation.trim() ? explanation.trim() : null,
                difficulty,
              })
            }
          >
            {isSaving ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
