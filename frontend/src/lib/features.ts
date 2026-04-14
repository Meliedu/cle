/**
 * Feature flags — toggled via NEXT_PUBLIC_* env vars at build time.
 *
 * Canvas integration is disabled by default until HKUST IT issues a
 * Developer Key. Set NEXT_PUBLIC_CANVAS_ENABLED=true to turn it on.
 */
export const CANVAS_ENABLED =
  process.env.NEXT_PUBLIC_CANVAS_ENABLED === "true";
