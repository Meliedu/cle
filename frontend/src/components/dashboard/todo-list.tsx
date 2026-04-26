"use client";

import { useCallback, useRef, useState } from "react";
import { format, parseISO } from "date-fns";
import { CalendarDays, Check, ListChecks, Plus, X } from "lucide-react";
import { DayPicker } from "react-day-picker";
import { cn } from "@/lib/utils";
import { useTodos, type TodoItem } from "@/hooks/use-todos";

function toIsoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function fromIso(iso?: string): Date | undefined {
  if (!iso) return undefined;
  try {
    return parseISO(iso);
  } catch {
    return undefined;
  }
}

export function TodoList() {
  const { items, add, toggle, remove, setDueDate } = useTodos();
  const [draft, setDraft] = useState("");
  const [draftDue, setDraftDue] = useState<Date | undefined>(undefined);
  const [pickerOpen, setPickerOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const openCount = items.filter((it) => !it.done).length;

  const submit = useCallback(() => {
    if (!draft.trim()) return;
    add(draft, draftDue ? toIsoDate(draftDue) : undefined);
    setDraft("");
    setDraftDue(undefined);
    setPickerOpen(false);
    inputRef.current?.focus();
  }, [draft, draftDue, add]);

  return (
    <section className="flex h-full flex-col rounded-[var(--radius-2xl)] border border-[var(--color-border)] bg-[var(--color-surface)]">
      <header className="flex items-center justify-between gap-3 border-b border-[var(--color-border)]/80 px-5 py-4">
        <div className="flex items-center gap-2">
          <ListChecks
            className="size-[18px] text-[var(--color-primary)]"
            strokeWidth={1.85}
          />
          <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
            To-do
          </h2>
          {openCount > 0 ? (
            <span className="rounded-full bg-[var(--color-primary-light)] px-2 py-0.5 text-[10px] font-semibold tabular-nums text-[var(--color-text-on-primary)]">
              {openCount}
            </span>
          ) : null}
        </div>
        <span className="text-[11px] text-[var(--color-text-muted)]">
          Stored locally
        </span>
      </header>

      {/* Compose row */}
      <div className="relative border-b border-[var(--color-border)]/60 px-5 py-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
          className="flex items-center gap-2"
        >
          <label htmlFor="todo-input" className="sr-only">
            New task
          </label>
          <input
            id="todo-input"
            ref={inputRef}
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Add a task…"
            className="flex-1 border-0 bg-transparent text-[14px] text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-0"
          />

          <button
            type="button"
            aria-label={
              draftDue
                ? `Due ${format(draftDue, "d MMM")} — change due date`
                : "Add due date"
            }
            onClick={() => setPickerOpen((v) => !v)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-[var(--radius-pill)] border px-2.5 py-1 text-[11px] font-medium transition-colors duration-[var(--duration-fast)]",
              draftDue
                ? "border-[var(--color-primary-muted)] bg-[var(--color-primary-light)] text-[var(--color-text-on-primary)]"
                : "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:border-[var(--color-border-hover)] hover:text-[var(--color-text-secondary)]"
            )}
          >
            <CalendarDays className="size-3" strokeWidth={2} />
            {draftDue ? format(draftDue, "d MMM") : "Due"}
          </button>

          <button
            type="submit"
            disabled={!draft.trim()}
            aria-label="Add task"
            className="inline-flex size-8 items-center justify-center rounded-full bg-[var(--color-text)] text-[var(--color-surface)] transition-opacity duration-[var(--duration-fast)] hover:bg-[var(--color-text-secondary)] disabled:cursor-not-allowed disabled:opacity-30"
          >
            <Plus className="size-4" strokeWidth={2.5} />
          </button>
        </form>

        {pickerOpen ? (
          <div
            role="dialog"
            aria-label="Pick due date"
            className="absolute right-4 top-[calc(100%+4px)] z-20 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-2 shadow-[var(--shadow-lg)]"
          >
            <DayPicker
              mode="single"
              selected={draftDue}
              onSelect={(d) => {
                setDraftDue(d ?? undefined);
                setPickerOpen(false);
              }}
              weekStartsOn={1}
              classNames={{ root: "meli-day-picker" }}
            />
            {draftDue ? (
              <button
                type="button"
                onClick={() => {
                  setDraftDue(undefined);
                  setPickerOpen(false);
                }}
                className="mx-auto mt-1 block rounded-[var(--radius-pill)] px-3 py-1 text-[11px] font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]"
              >
                Clear date
              </button>
            ) : null}
          </div>
        ) : null}
      </div>

      {/* Items */}
      <div className="flex-1 overflow-y-auto px-2 py-2">
        {items.length === 0 ? (
          <EmptyState />
        ) : (
          <ul className="space-y-0.5">
            {items.map((item) => (
              <TodoRow
                key={item.id}
                item={item}
                onToggle={toggle}
                onRemove={remove}
                onSetDueDate={setDueDate}
              />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

interface TodoRowProps {
  readonly item: TodoItem;
  readonly onToggle: (id: string) => void;
  readonly onRemove: (id: string) => void;
  readonly onSetDueDate: (id: string, dueDate: string | undefined) => void;
}

function TodoRow({ item, onToggle, onRemove, onSetDueDate }: TodoRowProps) {
  const [editingDate, setEditingDate] = useState(false);
  const due = fromIso(item.dueDate);

  return (
    <li
      className={cn(
        "group relative flex items-center gap-3 rounded-[var(--radius-md)] px-3 py-2 transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)]"
      )}
    >
      <button
        type="button"
        role="checkbox"
        aria-checked={item.done}
        aria-label={item.done ? "Mark as not done" : "Mark as done"}
        onClick={() => onToggle(item.id)}
        className={cn(
          "flex size-[18px] shrink-0 items-center justify-center rounded-[5px] border transition-colors duration-[var(--duration-fast)]",
          item.done
            ? "border-[var(--color-primary)] bg-[var(--color-primary)] text-[var(--color-text-on-primary)]"
            : "border-[var(--color-border-hover)] bg-[var(--color-surface)] hover:border-[var(--color-primary)]"
        )}
      >
        {item.done ? <Check className="size-3" strokeWidth={3} /> : null}
      </button>

      <span
        className={cn(
          "min-w-0 flex-1 truncate text-[14px] leading-snug transition-colors duration-[var(--duration-fast)]",
          item.done
            ? "text-[var(--color-text-muted)] line-through"
            : "text-[var(--color-text)]"
        )}
      >
        {item.text}
      </span>

      {due ? (
        <button
          type="button"
          onClick={() => setEditingDate((v) => !v)}
          aria-label={`Due ${format(due, "d MMM yyyy")} — change`}
          className="rounded-[var(--radius-pill)] bg-[var(--color-primary-light)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-text-on-primary)] transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-primary-muted)]"
        >
          {format(due, "d MMM")}
        </button>
      ) : (
        <button
          type="button"
          onClick={() => setEditingDate((v) => !v)}
          aria-label="Add due date"
          className="rounded-[var(--radius-pill)] border border-dashed border-[var(--color-border)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-text-muted)] opacity-0 transition-opacity duration-[var(--duration-fast)] hover:text-[var(--color-text-secondary)] group-hover:opacity-100"
        >
          Due
        </button>
      )}

      <button
        type="button"
        onClick={() => onRemove(item.id)}
        aria-label="Remove task"
        className="inline-flex size-6 items-center justify-center rounded-full text-[var(--color-text-muted)] opacity-0 transition-all duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-error)] group-hover:opacity-100"
      >
        <X className="size-3.5" strokeWidth={2} />
      </button>

      {editingDate ? (
        <div
          role="dialog"
          className="absolute right-4 top-[calc(100%-4px)] z-20 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-2 shadow-[var(--shadow-lg)]"
        >
          <DayPicker
            mode="single"
            selected={due}
            onSelect={(d) => {
              onSetDueDate(item.id, d ? toIsoDate(d) : undefined);
              setEditingDate(false);
            }}
            weekStartsOn={1}
            classNames={{ root: "meli-day-picker" }}
          />
          {due ? (
            <button
              type="button"
              onClick={() => {
                onSetDueDate(item.id, undefined);
                setEditingDate(false);
              }}
              className="mx-auto mt-1 block rounded-[var(--radius-pill)] px-3 py-1 text-[11px] font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]"
            >
              Clear date
            </button>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-1 px-4 py-10 text-center">
      <p className="text-[13px] font-medium text-[var(--color-text-secondary)]">
        Nothing on your list yet.
      </p>
      <p className="text-[12px] text-[var(--color-text-muted)]">
        Type a task above to begin.
      </p>
    </div>
  );
}
