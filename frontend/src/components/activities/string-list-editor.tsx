"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { GripVertical, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/patterns";
import { cn } from "@/lib/utils";

interface StringListEditorProps {
  /** The current list of entries (prompts / options / reactions). */
  readonly items: readonly string[];
  /** Emits the next immutable list on any add / edit / remove. */
  readonly onChange: (next: readonly string[]) => void;
  /** Placeholder for the add-row input. */
  readonly addPlaceholder: string;
  /** Accessible label for each row's text input. */
  readonly itemLabel: (index: number) => string;
  /** Empty-state title when there are no entries yet. */
  readonly emptyTitle: string;
  /** Empty-state reason. */
  readonly emptyReason: string;
}

/**
 * Reusable add / edit / remove editor for a flat list of short strings — the
 * shared config surface for swipe prompts, vote options, and comment reactions
 * (F4). Immutable throughout: every mutation emits a fresh array via `onChange`.
 * Keyboard-first (Enter adds a pending entry); a designed empty state renders
 * when the list is empty.
 */
export function StringListEditor({
  items,
  onChange,
  addPlaceholder,
  itemLabel,
  emptyTitle,
  emptyReason,
}: StringListEditorProps) {
  const t = useTranslations("teacher.activities.builder.list");
  const [draft, setDraft] = useState("");

  const addDraft = (): void => {
    const value = draft.trim();
    if (!value) return;
    onChange([...items, value]);
    setDraft("");
  };

  const editItem = (index: number, value: string): void => {
    onChange(items.map((item, i) => (i === index ? value : item)));
  };

  const removeItem = (index: number): void => {
    onChange(items.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-3">
      {items.length === 0 ? (
        <EmptyState
          className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] py-10"
          title={emptyTitle}
          reason={emptyReason}
        />
      ) : (
        <ul className="space-y-2">
          {items.map((item, index) => (
            <li
              key={index}
              className="flex items-center gap-2 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-2"
            >
              <GripVertical
                aria-hidden="true"
                className="size-4 shrink-0 text-[var(--color-text-muted)]"
              />
              <Input
                aria-label={itemLabel(index)}
                value={item}
                onChange={(e) => editItem(index, e.target.value)}
                className="h-8 border-transparent bg-transparent px-1.5 focus-visible:border-input"
              />
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={t("remove")}
                onClick={() => removeItem(index)}
              >
                <Trash2 className="text-[var(--color-error)]" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-center gap-2">
        <Input
          value={draft}
          placeholder={addPlaceholder}
          aria-label={addPlaceholder}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addDraft();
            }
          }}
          className={cn("h-9")}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={addDraft}
          disabled={draft.trim().length === 0}
        >
          <Plus />
          {t("add")}
        </Button>
      </div>
    </div>
  );
}
