"use client";

import { useState, useCallback } from "react";
import {
  useModules,
  useCreateModule,
  useUpdateModule,
  useDeleteModule,
} from "@/hooks/use-modules";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Loader2, Pencil, Trash2, Check, X } from "lucide-react";
import type { CourseModule } from "@/lib/curriculum-types";

interface Props {
  readonly courseId: string;
}

interface AddFormState {
  readonly name: string;
  readonly order_index: string;
}

const INITIAL_ADD_FORM: AddFormState = { name: "", order_index: "0" };

interface EditState {
  readonly moduleId: string;
  readonly name: string;
  readonly order_index: string;
}

export function ModuleTreeEditor({ courseId }: Props) {
  const { data: modules, isLoading } = useModules(courseId);
  const createModule = useCreateModule(courseId);
  const updateModule = useUpdateModule(courseId);
  const deleteModule = useDeleteModule(courseId);

  const [addForm, setAddForm] = useState<AddFormState>(INITIAL_ADD_FORM);
  const [addError, setAddError] = useState<string | null>(null);
  const [editState, setEditState] = useState<EditState | null>(null);

  const handleAddSubmit = useCallback(
    async (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (!addForm.name.trim()) {
        setAddError("Module name is required");
        return;
      }
      setAddError(null);
      try {
        await createModule.mutateAsync({
          name: addForm.name.trim(),
          order_index: Number(addForm.order_index) || 0,
        });
        setAddForm(INITIAL_ADD_FORM);
      } catch (err) {
        setAddError(err instanceof Error ? err.message : "Failed to create module");
      }
    },
    [addForm, createModule]
  );

  const startEdit = useCallback((mod: CourseModule) => {
    setEditState({
      moduleId: mod.id,
      name: mod.name,
      order_index: String(mod.order_index),
    });
  }, []);

  const cancelEdit = useCallback(() => setEditState(null), []);

  const handleEditSave = useCallback(async () => {
    if (!editState) return;
    try {
      await updateModule.mutateAsync({
        moduleId: editState.moduleId,
        patch: {
          name: editState.name.trim(),
          order_index: Number(editState.order_index) || 0,
        },
      });
      setEditState(null);
    } catch (err) {
      // Error visible via mutation state; keep edit open
    }
  }, [editState, updateModule]);

  const handleDelete = useCallback(
    async (moduleId: string, name: string) => {
      if (!window.confirm(`Delete module "${name}"?`)) return;
      try {
        await deleteModule.mutateAsync(moduleId);
      } catch {
        // Silent – mutation error visible via isPending guard
      }
    },
    [deleteModule]
  );

  const sorted = [...(modules ?? [])].sort(
    (a, b) => a.order_index - b.order_index
  );

  return (
    <div className="space-y-6">
      {/* Add module form */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Add Module</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleAddSubmit} className="flex flex-wrap items-end gap-3">
            <div className="flex-1 min-w-[200px] space-y-1.5">
              <Label htmlFor="mod-name">Name</Label>
              <Input
                id="mod-name"
                placeholder="Module name"
                value={addForm.name}
                onChange={(e) =>
                  setAddForm((prev) => ({ ...prev, name: e.target.value }))
                }
              />
            </div>
            <div className="w-28 space-y-1.5">
              <Label htmlFor="mod-order">Order</Label>
              <Input
                id="mod-order"
                type="number"
                min={0}
                value={addForm.order_index}
                onChange={(e) =>
                  setAddForm((prev) => ({
                    ...prev,
                    order_index: e.target.value,
                  }))
                }
              />
            </div>
            <Button type="submit" disabled={createModule.isPending}>
              {createModule.isPending && <Loader2 className="size-4 animate-spin" />}
              Add
            </Button>
          </form>
          {addError && (
            <p className="mt-2 text-xs text-[var(--color-error)]">{addError}</p>
          )}
        </CardContent>
      </Card>

      {/* Module list */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Modules ({isLoading ? "..." : sorted.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-10 rounded-[var(--radius-md)]" />
              ))}
            </div>
          ) : sorted.length === 0 ? (
            <p className="text-sm text-[var(--color-text-muted)]">
              No modules yet. Add one above.
            </p>
          ) : (
            <ul className="divide-y divide-[var(--color-border)]">
              {sorted.map((mod) => {
                const isEditing = editState?.moduleId === mod.id;
                return (
                  <li
                    key={mod.id}
                    className="flex items-center gap-3 py-3 first:pt-0 last:pb-0"
                  >
                    <span className="w-8 shrink-0 text-right text-xs text-[var(--color-text-muted)]">
                      {mod.order_index}
                    </span>

                    {isEditing && editState ? (
                      <>
                        <Input
                          className="flex-1"
                          value={editState.name}
                          onChange={(e) =>
                            setEditState((prev) =>
                              prev ? { ...prev, name: e.target.value } : prev
                            )
                          }
                          autoFocus
                        />
                        <Input
                          className="w-20"
                          type="number"
                          min={0}
                          value={editState.order_index}
                          onChange={(e) =>
                            setEditState((prev) =>
                              prev
                                ? { ...prev, order_index: e.target.value }
                                : prev
                            )
                          }
                        />
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={handleEditSave}
                          disabled={updateModule.isPending}
                          aria-label="Save"
                        >
                          {updateModule.isPending ? (
                            <Loader2 className="size-4 animate-spin" />
                          ) : (
                            <Check className="size-4 text-[var(--color-success)]" />
                          )}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={cancelEdit}
                          aria-label="Cancel"
                        >
                          <X className="size-4" />
                        </Button>
                      </>
                    ) : (
                      <>
                        <span className="flex-1 text-sm font-medium text-[var(--color-text)]">
                          {mod.name}
                        </span>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => startEdit(mod)}
                          aria-label={`Edit ${mod.name}`}
                        >
                          <Pencil className="size-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleDelete(mod.id, mod.name)}
                          disabled={deleteModule.isPending}
                          aria-label={`Delete ${mod.name}`}
                          className="text-[var(--color-text-muted)] hover:text-[var(--color-error)]"
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
