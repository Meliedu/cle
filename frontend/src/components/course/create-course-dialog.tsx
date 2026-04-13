"use client";

import { useState, useCallback } from "react";
import { useAuth } from "@clerk/nextjs";
import { useQueryClient } from "@tanstack/react-query";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Loader2 } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface CreateCourseDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}

interface FormState {
  readonly name: string;
  readonly code: string;
  readonly language: string;
  readonly semester: string;
  readonly description: string;
}

const initialForm: FormState = {
  name: "",
  code: "",
  language: "",
  semester: "",
  description: "",
};

const languages = ["Chinese", "English", "Japanese", "Korean"] as const;

interface FormErrors {
  readonly name?: string;
  readonly code?: string;
  readonly language?: string;
  readonly semester?: string;
}

function validateForm(form: FormState): FormErrors {
  const errors: Record<string, string> = {};

  if (!form.name.trim()) {
    errors.name = "Course name is required";
  }
  if (!form.code.trim()) {
    errors.code = "Course code is required";
  }
  if (!form.language) {
    errors.language = "Please select a language";
  }
  if (!form.semester.trim()) {
    errors.semester = "Semester is required";
  }

  return errors;
}

export function CreateCourseDialog({
  open,
  onOpenChange,
}: CreateCourseDialogProps) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>(initialForm);
  const [errors, setErrors] = useState<FormErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const updateField = useCallback(
    <K extends keyof FormState>(field: K, value: FormState[K]) => {
      setForm((prev) => ({ ...prev, [field]: value }));
      // Clear error on change
      setErrors((prev) => {
        if (prev[field as keyof FormErrors]) {
          const next = { ...prev };
          delete next[field as keyof FormErrors];
          return next;
        }
        return prev;
      });
    },
    []
  );

  const handleSubmit = useCallback(
    async (e: { preventDefault: () => void }) => {
      e.preventDefault();
      const validationErrors = validateForm(form);

      if (Object.keys(validationErrors).length > 0) {
        setErrors(validationErrors);
        return;
      }

      setIsSubmitting(true);
      setSubmitError(null);

      try {
        const token = await getToken();
        if (!token) throw new Error("Not authenticated");
        await apiFetch<{ success: boolean; data: unknown }>("/courses", {
          method: "POST",
          token,
          body: JSON.stringify({
            name: form.name.trim(),
            code: form.code.trim() || null,
            description: form.description.trim() || null,
            language: form.language,
            semester: form.semester.trim() || null,
            settings: {},
          }),
        });
        await queryClient.invalidateQueries({ queryKey: ["courses"] });
        onOpenChange(false);
        setForm(initialForm);
        setErrors({});
      } catch (error: unknown) {
        const message =
          error instanceof Error ? error.message : "Failed to create course";
        setSubmitError(message);
      } finally {
        setIsSubmitting(false);
      }
    },
    [form, onOpenChange, getToken, queryClient]
  );

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen) {
        setForm(initialForm);
        setErrors({});
        setSubmitError(null);
      }
      onOpenChange(nextOpen);
    },
    [onOpenChange]
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Create Course</DialogTitle>
          <DialogDescription>
            Set up a new language course for your students.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Name */}
          <div className="space-y-1.5">
            <Label htmlFor="course-name">
              Course Name <span className="text-[var(--color-error)]">*</span>
            </Label>
            <Input
              id="course-name"
              placeholder="e.g. Chinese for Beginners"
              value={form.name}
              onChange={(e) => updateField("name", e.target.value)}
              aria-invalid={!!errors.name}
              aria-describedby={errors.name ? "course-name-error" : undefined}
            />
            {errors.name && (
              <p id="course-name-error" className="text-xs text-[var(--color-error)]">
                {errors.name}
              </p>
            )}
          </div>

          {/* Code */}
          <div className="space-y-1.5">
            <Label htmlFor="course-code">
              Course Code <span className="text-[var(--color-error)]">*</span>
            </Label>
            <Input
              id="course-code"
              placeholder="e.g. LANG1010"
              value={form.code}
              onChange={(e) => updateField("code", e.target.value)}
              aria-invalid={!!errors.code}
              aria-describedby={errors.code ? "course-code-error" : undefined}
            />
            {errors.code && (
              <p id="course-code-error" className="text-xs text-[var(--color-error)]">
                {errors.code}
              </p>
            )}
          </div>

          {/* Language */}
          <div className="space-y-1.5">
            <Label>
              Language <span className="text-[var(--color-error)]">*</span>
            </Label>
            <Select
              value={form.language}
              onValueChange={(val) => updateField("language", val ?? "")}
            >
              <SelectTrigger
                className="w-full"
                aria-invalid={!!errors.language}
                aria-describedby={errors.language ? "course-language-error" : undefined}
              >
                <SelectValue placeholder="Select language" />
              </SelectTrigger>
              <SelectContent>
                {languages.map((lang) => (
                  <SelectItem key={lang} value={lang}>
                    {lang}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.language && (
              <p id="course-language-error" className="text-xs text-[var(--color-error)]">
                {errors.language}
              </p>
            )}
          </div>

          {/* Semester */}
          <div className="space-y-1.5">
            <Label htmlFor="course-semester">
              Semester <span className="text-[var(--color-error)]">*</span>
            </Label>
            <Input
              id="course-semester"
              placeholder="e.g. 2025 Spring"
              value={form.semester}
              onChange={(e) => updateField("semester", e.target.value)}
              aria-invalid={!!errors.semester}
              aria-describedby={errors.semester ? "course-semester-error" : undefined}
            />
            {errors.semester && (
              <p id="course-semester-error" className="text-xs text-[var(--color-error)]">
                {errors.semester}
              </p>
            )}
          </div>

          {/* Description */}
          <div className="space-y-1.5">
            <Label htmlFor="course-description">Description</Label>
            <Textarea
              id="course-description"
              placeholder="Brief description of the course..."
              value={form.description}
              onChange={(e) => updateField("description", e.target.value)}
              rows={3}
            />
          </div>

          {submitError && (
            <p className="text-sm text-[var(--color-error)]">{submitError}</p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting && <Loader2 className="size-4 animate-spin" />}
              {isSubmitting ? "Creating..." : "Create Course"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
