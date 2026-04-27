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

interface FlashcardCardLike {
  readonly front: string;
  readonly back: string;
  readonly difficulty?: string;
}

interface DraftCard {
  front: string;
  back: string;
  difficulty: string;
}

const EMPTY: DraftCard = { front: "", back: "", difficulty: "medium" };

interface FlashcardCardEditorProps {
  readonly mode: "create" | "edit";
  readonly open: boolean;
  readonly initial: FlashcardCardLike | null;
  readonly isSaving: boolean;
  readonly onCancel: () => void;
  readonly onSubmit: (draft: DraftCard) => void;
}

export function FlashcardCardEditor({
  mode,
  open,
  initial,
  isSaving,
  onCancel,
  onSubmit,
}: FlashcardCardEditorProps) {
  const [draft, setDraft] = useState<DraftCard>(EMPTY);

  useEffect(() => {
    if (!open) return;
    if (initial) {
      setDraft({
        front: initial.front,
        back: initial.back,
        difficulty:
          initial.difficulty &&
          (DIFFICULTIES as readonly string[]).includes(initial.difficulty)
            ? initial.difficulty
            : "medium",
      });
    } else {
      setDraft(EMPTY);
    }
  }, [open, initial]);

  const front = draft.front.trim();
  const back = draft.back.trim();
  const canSubmit = front.length > 0 && back.length > 0 && !isSaving;

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) onCancel();
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {mode === "create" ? "Add Card" : "Edit Card"}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="card-front">
              Front <span className="text-[var(--color-error)]">*</span>
            </Label>
            <Textarea
              id="card-front"
              value={draft.front}
              onChange={(e) =>
                setDraft((d) => ({ ...d, front: e.target.value }))
              }
              rows={2}
              maxLength={500}
              placeholder="Question / prompt"
              disabled={isSaving}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="card-back">
              Back <span className="text-[var(--color-error)]">*</span>
            </Label>
            <Textarea
              id="card-back"
              value={draft.back}
              onChange={(e) =>
                setDraft((d) => ({ ...d, back: e.target.value }))
              }
              rows={4}
              maxLength={2000}
              placeholder="Answer / explanation"
              disabled={isSaving}
            />
          </div>

          <div className="space-y-1.5">
            <Label>Difficulty</Label>
            <Select
              value={draft.difficulty}
              onValueChange={(v) =>
                setDraft((d) => ({ ...d, difficulty: v ?? "medium" }))
              }
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
                front,
                back,
                difficulty: draft.difficulty,
              })
            }
          >
            {isSaving
              ? "Saving..."
              : mode === "create"
                ? "Add"
                : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
