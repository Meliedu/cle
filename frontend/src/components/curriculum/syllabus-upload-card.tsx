"use client";

import { useRef, useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Upload, Loader2, CheckCircle, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/hooks/use-auth";
import { useTriggerSyllabusImport } from "@/hooks/use-syllabus";
import { API_URL } from "@/lib/api";

interface Props {
  readonly courseId: string;
}

type UploadState =
  | { kind: "idle" }
  | { kind: "uploading" }
  | { kind: "triggering" }
  | { kind: "done" }
  | { kind: "error"; message: string };

const ACCEPTED_EXTENSIONS = ".pdf,.docx";

export function SyllabusUploadCard({ courseId }: Props) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const triggerImport = useTriggerSyllabusImport(courseId);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>({ kind: "idle" });

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0] ?? null;
      setSelectedFile(file);
      setUploadState({ kind: "idle" });
    },
    []
  );

  const handleSubmit = useCallback(
    async (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();

      if (!selectedFile) return;

      const token = await getToken({ template: "backend" });
      if (!token) {
        setUploadState({ kind: "error", message: "Not authenticated" });
        return;
      }

      setUploadState({ kind: "uploading" });

      let documentId: string;

      try {
        const formData = new FormData();
        formData.append("file", selectedFile);
        formData.append("kind", "syllabus");

        const res = await fetch(
          `${API_URL}/courses/${courseId}/documents/upload`,
          {
            method: "POST",
            headers: { Authorization: `Bearer ${token}` },
            body: formData,
          }
        );

        if (!res.ok) {
          const payload = (await res.json().catch(() => null)) as
            | { error?: { message?: string }; detail?: string }
            | null;
          const msg =
            payload?.error?.message ??
            payload?.detail ??
            `Upload failed (${res.status})`;
          setUploadState({ kind: "error", message: msg });
          return;
        }

        const data = (await res.json()) as {
          data?: { id?: string };
        };
        documentId = data.data?.id ?? "";
        if (!documentId) {
          setUploadState({ kind: "error", message: "Upload succeeded but got no document ID" });
          return;
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Network error";
        setUploadState({ kind: "error", message: msg });
        return;
      }

      setUploadState({ kind: "triggering" });

      try {
        await triggerImport.mutateAsync(documentId);
        await queryClient.invalidateQueries({
          queryKey: ["syllabus-imports", courseId],
        });
        setUploadState({ kind: "done" });
        setSelectedFile(null);
        if (fileInputRef.current) {
          fileInputRef.current.value = "";
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to trigger import";
        setUploadState({ kind: "error", message: msg });
      }
    },
    [selectedFile, courseId, getToken, triggerImport, queryClient]
  );

  const isLoading =
    uploadState.kind === "uploading" || uploadState.kind === "triggering";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Upload className="size-4" />
          Upload Syllabus
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="syllabus-file">Syllabus file</Label>
            <Input
              id="syllabus-file"
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_EXTENSIONS}
              onChange={handleFileChange}
              disabled={isLoading}
            />
            <p className="text-xs text-[var(--color-text-muted)]">
              Accepted: PDF, DOCX
            </p>
          </div>

          {uploadState.kind === "error" && (
            <div className="flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-error)] bg-[var(--color-error-light)] px-3 py-2 text-sm text-[var(--color-error)]">
              <AlertCircle className="size-4 shrink-0" />
              {uploadState.message}
            </div>
          )}

          {uploadState.kind === "done" && (
            <div className="flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-success)] bg-[var(--color-success-light)] px-3 py-2 text-sm text-[var(--color-success)]">
              <CheckCircle className="size-4 shrink-0" />
              Syllabus uploaded and import triggered. Check the list below for
              status.
            </div>
          )}

          <Button
            type="submit"
            disabled={!selectedFile || isLoading}
            className="w-full sm:w-auto"
          >
            {isLoading && <Loader2 className="mr-2 size-4 animate-spin" />}
            {uploadState.kind === "uploading"
              ? "Uploading…"
              : uploadState.kind === "triggering"
                ? "Starting import…"
                : "Upload syllabus"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
