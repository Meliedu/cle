"use client";

import { useState, useCallback, useRef } from "react";
import { useAuth } from "@/hooks/use-auth";
import { useQueryClient } from "@tanstack/react-query";
import { Upload, FileText, X, Loader2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { API_URL } from "@/lib/api";

const ACCEPTED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "video/mp4",
  "audio/mpeg",
] as const;

const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".pptx", ".mp4", ".mp3"];

const MAX_FILE_SIZE = 100 * 1024 * 1024; // 100MB

interface UploadFile {
  readonly file: File;
  readonly id: string;
  readonly progress: number;
  readonly status: "uploading" | "done" | "error";
  readonly errorMessage?: string;
}

interface UploadZoneProps {
  readonly courseId: string;
  readonly onUploadComplete?: () => void;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isAcceptedType(file: File): boolean {
  if (ACCEPTED_TYPES.includes(file.type as (typeof ACCEPTED_TYPES)[number])) {
    return true;
  }
  const ext = `.${file.name.split(".").pop()?.toLowerCase()}`;
  return ACCEPTED_EXTENSIONS.includes(ext);
}

export function UploadZone({ courseId, onUploadComplete }: UploadZoneProps) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const [isDragOver, setIsDragOver] = useState(false);
  const [files, setFiles] = useState<readonly UploadFile[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortControllersRef = useRef<Map<string, XMLHttpRequest>>(new Map());

  const uploadFile = useCallback(
    async (uploadFile: UploadFile) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const formData = new FormData();
      formData.append("file", uploadFile.file);

      const xhr = new XMLHttpRequest();
      abortControllersRef.current.set(uploadFile.id, xhr);

      xhr.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) {
          const progress = (event.loaded / event.total) * 100;
          setFiles((prev) =>
            prev.map((f) =>
              f.id === uploadFile.id ? { ...f, progress } : f
            )
          );
        }
      });

      xhr.addEventListener("load", () => {
        abortControllersRef.current.delete(uploadFile.id);
        if (xhr.status >= 200 && xhr.status < 300) {
          setFiles((prev) =>
            prev.map((f) =>
              f.id === uploadFile.id
                ? { ...f, progress: 100, status: "done" }
                : f
            )
          );
          void queryClient.invalidateQueries({
            queryKey: ["documents", courseId],
          });
          onUploadComplete?.();
        } else {
          let errorMessage = `Upload failed (${xhr.status})`;
          try {
            const response = JSON.parse(xhr.responseText);
            if (response.error?.message) {
              errorMessage = response.error.message;
            } else if (response.detail) {
              errorMessage = response.detail;
            }
          } catch {
            // Use the default error message
          }
          setFiles((prev) =>
            prev.map((f) =>
              f.id === uploadFile.id
                ? { ...f, status: "error", errorMessage }
                : f
            )
          );
        }
      });

      xhr.addEventListener("error", () => {
        abortControllersRef.current.delete(uploadFile.id);
        setFiles((prev) =>
          prev.map((f) =>
            f.id === uploadFile.id
              ? { ...f, status: "error", errorMessage: "Network error" }
              : f
          )
        );
      });

      xhr.open(
        "POST",
        `${API_URL}/courses/${courseId}/documents/upload`
      );
      if (token) {
        xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      }
      xhr.send(formData);
    },
    [courseId, getToken, onUploadComplete, queryClient]
  );

  const processFiles = useCallback(
    (fileList: FileList | File[]) => {
      const newFiles: UploadFile[] = [];

      for (const file of Array.from(fileList)) {
        const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;

        if (!isAcceptedType(file)) {
          newFiles.push({
            file,
            id,
            progress: 0,
            status: "error",
            errorMessage: "Unsupported file type",
          });
          continue;
        }

        if (file.size > MAX_FILE_SIZE) {
          newFiles.push({
            file,
            id,
            progress: 0,
            status: "error",
            errorMessage: "File exceeds 100MB limit",
          });
          continue;
        }

        const entry: UploadFile = {
          file,
          id,
          progress: 0,
          status: "uploading",
        };
        newFiles.push(entry);

        void uploadFile(entry);
      }

      setFiles((prev) => [...prev, ...newFiles]);
    },
    [uploadFile]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragOver(false);

      if (e.dataTransfer.files.length > 0) {
        processFiles(e.dataTransfer.files);
      }
    },
    [processFiles]
  );

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        processFiles(e.target.files);
        e.target.value = "";
      }
    },
    [processFiles]
  );

  const handleClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const removeFile = useCallback((id: string) => {
    const xhr = abortControllersRef.current.get(id);
    if (xhr) {
      xhr.abort();
      abortControllersRef.current.delete(id);
    }
    setFiles((prev) => prev.filter((f) => f.id !== id));
  }, []);

  return (
    <div className="space-y-4">
      {/* Drop zone */}
      <button
        type="button"
        onClick={handleClick}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          "flex w-full cursor-pointer flex-col items-center gap-3 rounded-[var(--radius-lg)] border-2 border-dashed p-8 text-center transition-all duration-[var(--duration-normal)]",
          isDragOver
            ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]"
            : "border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-border-hover)] hover:bg-[var(--color-surface-hover)]"
        )}
      >
        <div
          className={cn(
            "flex size-12 items-center justify-center rounded-full transition-colors duration-[var(--duration-fast)]",
            isDragOver
              ? "bg-[var(--color-primary)] text-white"
              : "bg-[var(--color-primary-light)] text-[var(--color-primary)]"
          )}
        >
          <Upload className="size-5" />
        </div>
        <div>
          <p className="text-sm font-medium text-[var(--color-text)]">
            {isDragOver ? "Drop files here" : "Drag & drop files or click to browse"}
          </p>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            PDF, DOCX, PPTX, MP4, MP3 - Max 100MB
          </p>
        </div>
      </button>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={ACCEPTED_EXTENSIONS.join(",")}
        onChange={handleFileSelect}
        className="hidden"
        aria-label="Upload files"
      />

      {/* File list */}
      {files.length > 0 && (
        <ul className="space-y-2">
          {files.map((uploadFile) => (
            <li
              key={uploadFile.id}
              className="flex items-center gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-3"
            >
              <FileText
                className={cn(
                  "size-5 shrink-0",
                  uploadFile.status === "error"
                    ? "text-[var(--color-error)]"
                    : "text-[var(--color-primary)]"
                )}
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-[var(--color-text)]">
                  {uploadFile.file.name}
                </p>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-[var(--color-text-muted)]">
                    {formatFileSize(uploadFile.file.size)}
                  </span>
                  {uploadFile.status === "error" && (
                    <span className="flex items-center gap-1 text-xs text-[var(--color-error)]">
                      <AlertCircle className="size-3" />
                      {uploadFile.errorMessage}
                    </span>
                  )}
                </div>
                {uploadFile.status === "uploading" && (
                  <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-[var(--color-border)]">
                    <div
                      className="h-full rounded-full bg-[var(--color-primary)] transition-[width] duration-300"
                      style={{ width: `${uploadFile.progress}%` }}
                    />
                  </div>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {uploadFile.status === "uploading" && (
                  <Loader2 className="size-4 animate-spin text-[var(--color-primary)]" />
                )}
                {uploadFile.status === "done" && (
                  <span className="text-xs font-medium text-[var(--color-success)]">
                    Done
                  </span>
                )}
                <button
                  onClick={() => removeFile(uploadFile.id)}
                  className="rounded-[var(--radius-sm)] p-1 text-[var(--color-text-muted)] transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)]"
                  aria-label={`Remove ${uploadFile.file.name}`}
                >
                  <X className="size-4" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
