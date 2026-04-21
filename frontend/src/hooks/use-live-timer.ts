import { useEffect, useRef, useState } from "react";

/**
 * Wall-clock countdown anchored to the server's reported `elapsedSeconds`.
 *
 * Both host and student consume the same `/state` poll, so if both sides run
 * this hook they will stay in sync within ~ one network round-trip. The
 * anchor is recomputed once per question (or on large drift) — NOT on every
 * poll — so the local ticker reads smoothly instead of jumping 1–2s each
 * time a new poll lands.
 *
 * Returns whole seconds remaining (ceil'd), clamped to [0, timeLimit].
 */
export function useLiveTimer(
  questionIndex: number | null | undefined,
  timeLimit: number,
  elapsedSeconds: number
): number {
  const anchorRef = useRef<{ index: number; anchorMs: number }>({
    index: -1,
    anchorMs: 0,
  });
  const [now, setNow] = useState<number>(() => Date.now());

  /* Re-anchor when a new question arrives, or when the server's reported
   * elapsed differs from ours by >1s (indicates a backend restart or clock
   * skew — trust the server over our local tick). */
  useEffect(() => {
    if (questionIndex == null || questionIndex < 0) return;
    const desiredAnchor = Date.now() - elapsedSeconds * 1000;
    const drift = Math.abs(anchorRef.current.anchorMs - desiredAnchor);
    if (
      anchorRef.current.index !== questionIndex ||
      drift > 1000
    ) {
      anchorRef.current = { index: questionIndex, anchorMs: desiredAnchor };
    }
  }, [questionIndex, elapsedSeconds]);

  /* Re-render 4×/s so the displayed countdown is smooth. Interval is gated
   * on having an active question so we don't spin while in the lobby. */
  useEffect(() => {
    if (questionIndex == null || questionIndex < 0) return;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [questionIndex]);

  if (questionIndex == null || questionIndex < 0) return 0;
  /* On the first render after a new question arrives, the ref still holds
   * the previous question's anchor (the sync effect above hasn't run yet —
   * effects fire post-commit). Using the stale anchor returns 0 for one
   * frame, which briefly flips the host panel into the "time up / reveal"
   * state and leaks the correct answer in green. Derive a fresh anchor
   * locally; the effect persists a nearly-identical value for subsequent
   * renders (same formula, same elapsedSeconds, Date.now() drifts by <1ms).
   *
   * Strict-mode note: Date.now() in render is technically an impurity —
   * double-invoke gets two different clock reads. Both values collapse to
   * the same integer through Math.ceil + clamp in practice, and the
   * committed render's value is what users observe. Accepted. */
  const anchorMs =
    anchorRef.current.index === questionIndex
      ? anchorRef.current.anchorMs
      : Date.now() - elapsedSeconds * 1000;
  const elapsedLocal = (now - anchorMs) / 1000;
  const remaining = Math.ceil(timeLimit - elapsedLocal);
  return Math.max(0, Math.min(timeLimit, remaining));
}
