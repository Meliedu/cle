import {
  FileText,
  FileType2,
  Presentation,
  Video,
  AudioLines,
  Link as LinkIcon,
  File as FileIcon,
  type LucideIcon,
} from "lucide-react";

import type { DocumentResponse } from "@/hooks/use-documents";
import type { StatusTone } from "@/components/course/session-status";

/**
 * Presentation helpers for the teacher materials library (F6/F7). Kept
 * copy-free — every label is a next-intl key under `teacher.materials.*`,
 * resolved by the caller. These map a `DocumentResponse` onto a stable file
 * "kind" (icon + type-label key) and a processing-status tone so the same file
 * always reads the same across the table, folders, and detail panel.
 */

export type MaterialKind =
  | "pdf"
  | "docx"
  | "pptx"
  | "video"
  | "audio"
  | "link"
  | "file";

const EXTENSION_KIND: Readonly<Record<string, MaterialKind>> = {
  pdf: "pdf",
  doc: "docx",
  docx: "docx",
  ppt: "pptx",
  pptx: "pptx",
  mp4: "video",
  mov: "video",
  webm: "video",
  mp3: "audio",
  m4a: "audio",
  wav: "audio",
};

const MIME_KIND: readonly (readonly [string, MaterialKind])[] = [
  ["pdf", "pdf"],
  ["presentation", "pptx"],
  ["powerpoint", "pptx"],
  ["word", "docx"],
  ["document", "docx"],
  ["video", "video"],
  ["audio", "audio"],
];

/** Derive a stable file kind from a document's filename / MIME type. */
export function materialKind(doc: DocumentResponse): MaterialKind {
  const ext = doc.filename.split(".").pop()?.toLowerCase();
  if (ext && EXTENSION_KIND[ext]) return EXTENSION_KIND[ext];

  const type = doc.file_type?.toLowerCase() ?? "";
  for (const [needle, kind] of MIME_KIND) {
    if (type.includes(needle)) return kind;
  }
  return "file";
}

const KIND_ICON: Readonly<Record<MaterialKind, LucideIcon>> = {
  pdf: FileText,
  docx: FileType2,
  pptx: Presentation,
  video: Video,
  audio: AudioLines,
  link: LinkIcon,
  file: FileIcon,
};

/**
 * Decorative Lucide icon for a file kind. A module-scope component (rather than
 * `const Icon = pick(kind)` at each call site) so it reads as a stable
 * component to the React Compiler, and is always `aria-hidden`.
 */
export function MaterialKindIcon({
  kind,
  className,
}: {
  readonly kind: MaterialKind;
  readonly className?: string;
}) {
  const Icon = KIND_ICON[kind];
  return <Icon aria-hidden="true" className={className} />;
}

/** Processing-status → i18n key (`teacher.materials.docStatus.*`) + chip tone. */
export function materialStatus(
  status: string
): { readonly key: string; readonly tone: StatusTone } {
  switch (status) {
    case "ready":
      return { key: "ready", tone: "success" };
    case "processing":
      return { key: "processing", tone: "progress" };
    case "pending":
      return { key: "pending", tone: "neutral" };
    case "error":
    case "failed":
      return { key: "failed", tone: "muted" };
    default:
      return { key: "pending", tone: "neutral" };
  }
}

/** Human-readable byte size (mirrors the upload-zone formatting). */
export function formatFileSize(bytes: number | null): string | null {
  if (bytes == null) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
