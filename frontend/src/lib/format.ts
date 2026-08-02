/**
 * Format a byte count to a human-readable string (e.g. "2.4 MB").
 */
export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes == null || bytes === 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

/**
 * Format an ISO date string to a relative time string (e.g. "2 hours ago").
 */
export function formatRelativeTime(isoDate: string): string {
  const date = new Date(isoDate);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();

  if (diffMs < 0) return "just now";

  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return "just now";

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return minutes === 1 ? "1 minute ago" : `${minutes} minutes ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return hours === 1 ? "1 hour ago" : `${hours} hours ago`;

  const days = Math.floor(hours / 24);
  if (days < 30) return days === 1 ? "1 day ago" : `${days} days ago`;

  const months = Math.floor(days / 30);
  if (months < 12) return months === 1 ? "1 month ago" : `${months} months ago`;

  const years = Math.floor(months / 12);
  return years === 1 ? "1 year ago" : `${years} years ago`;
}

/**
 * The course name without a repeated code prefix.
 *
 * Course names in the wild often already start with the code
 * ("LANG1511 · Chinese I for Non-Chinese Speakers"), so rendering the code as
 * the heading and the raw name beneath it says the code twice. Every surface
 * that renders "code · name" (or code above name) must pass the name through
 * this first.
 */
export function courseTitle(code: string | null, name: string): string {
  const trimmed = name.trim();
  if (!code || !trimmed.toLowerCase().startsWith(code.toLowerCase())) {
    return trimmed;
  }
  // The match must end on a token boundary: "LANG151" must not bite into
  // "LANG1511 · Chinese I" and return "1 · Chinese I".
  const rest = trimmed.slice(code.length);
  if (rest.length > 0 && !/^[\s·:\-–—]/.test(rest)) {
    return trimmed;
  }
  // Drop the code and any separator that followed it.
  return rest.replace(/^\s*[·:\-–—]\s*/, "").trim() || trimmed;
}

/**
 * A course's language for display. The column is free text ("chinese",
 * "Chinese"), so title-case it rather than render raw metadata casing.
 */
export function displayLanguage(language: string): string {
  return language
    .trim()
    .split(/\s+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

/**
 * Derive the file type label from a filename.
 */
export function getFileTypeLabel(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  switch (ext) {
    case "pdf":
      return "PDF";
    case "docx":
      return "DOCX";
    case "pptx":
      return "PPTX";
    case "mp4":
      return "MP4";
    case "mp3":
      return "MP3";
    default:
      return ext.toUpperCase() || "FILE";
  }
}
