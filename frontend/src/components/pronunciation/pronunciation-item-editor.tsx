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
import type {
  PronunciationItemResponse,
  PronunciationItemType,
} from "@/hooks/use-pronunciation-sets";

const ITEM_TYPES: readonly PronunciationItemType[] = [
  "word",
  "phrase",
  "sentence",
];
const DIFFICULTIES = ["easy", "medium", "hard"] as const;

interface DraftItem {
  text: string;
  item_type: PronunciationItemType;
  phonetic: string;
  translation: string;
  tips: string;
  difficulty: string;
}

const EMPTY: DraftItem = {
  text: "",
  item_type: "word",
  phonetic: "",
  translation: "",
  tips: "",
  difficulty: "medium",
};

interface PronunciationItemEditorProps {
  readonly mode: "create" | "edit";
  readonly open: boolean;
  readonly initial: PronunciationItemResponse | null;
  readonly isSaving: boolean;
  readonly onCancel: () => void;
  readonly onSubmit: (draft: DraftItem) => void;
}

export function PronunciationItemEditor({
  mode,
  open,
  initial,
  isSaving,
  onCancel,
  onSubmit,
}: PronunciationItemEditorProps) {
  const [draft, setDraft] = useState<DraftItem>(EMPTY);

  useEffect(() => {
    if (!open) return;
    if (initial) {
      setDraft({
        text: initial.text,
        item_type: initial.item_type,
        phonetic: initial.phonetic ?? "",
        translation: initial.translation ?? "",
        tips: initial.tips ?? "",
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

  const trimmedText = draft.text.trim();
  const canSubmit = trimmedText.length > 0 && !isSaving;

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
            {mode === "create" ? "Add Item" : "Edit Item"}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="item-text">
              Text <span className="text-[var(--color-error)]">*</span>
            </Label>
            <Textarea
              id="item-text"
              value={draft.text}
              onChange={(e) =>
                setDraft((d) => ({ ...d, text: e.target.value }))
              }
              rows={2}
              maxLength={500}
              placeholder="Word, phrase, or sentence to pronounce"
              disabled={isSaving}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Item type</Label>
              <Select
                value={draft.item_type}
                onValueChange={(v) =>
                  setDraft((d) => ({
                    ...d,
                    item_type: (v as PronunciationItemType) ?? "word",
                  }))
                }
                disabled={isSaving}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ITEM_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      <span className="capitalize">{t}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
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

          <div className="space-y-1.5">
            <Label htmlFor="item-phonetic">Phonetic (IPA, optional)</Label>
            <Input
              id="item-phonetic"
              value={draft.phonetic}
              onChange={(e) =>
                setDraft((d) => ({ ...d, phonetic: e.target.value }))
              }
              maxLength={500}
              placeholder="e.g. /prəˌnʌn.siˈeɪ.ʃən/"
              disabled={isSaving}
              className="font-mono"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="item-translation">Translation (optional)</Label>
            <Input
              id="item-translation"
              value={draft.translation}
              onChange={(e) =>
                setDraft((d) => ({ ...d, translation: e.target.value }))
              }
              maxLength={1000}
              disabled={isSaving}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="item-tips">Tips (optional)</Label>
            <Textarea
              id="item-tips"
              value={draft.tips}
              onChange={(e) =>
                setDraft((d) => ({ ...d, tips: e.target.value }))
              }
              rows={2}
              maxLength={2000}
              placeholder="e.g. stress on the second syllable"
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
            onClick={() => onSubmit({ ...draft, text: trimmedText })}
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
