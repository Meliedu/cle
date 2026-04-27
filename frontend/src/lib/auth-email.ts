// Transactional email via Resend. Used by Better Auth for email verification
// and password reset. Templates are deliberately plain text + minimal HTML —
// Phase 2.5 of the migration plan owns the polish pass.

import { Resend } from "resend";

const apiKey = process.env.RESEND_API_KEY;
const fromEmail = process.env.RESEND_FROM_EMAIL ?? "Meli <noreply@meli.app>";

const resend = apiKey ? new Resend(apiKey) : null;

type SendArgs = {
  to: string;
  subject: string;
  text: string;
  html: string;
};

async function send({ to, subject, text, html }: SendArgs): Promise<void> {
  if (!resend) {
    // In dev without a Resend key, log instead of failing — lets the auth
    // flow proceed so engineers can still test signup. Production raises.
    if (process.env.NODE_ENV === "production") {
      throw new Error("RESEND_API_KEY is not configured");
    }
    // Body intentionally omitted — it contains the verification / reset
    // token URL, which is single-use auth material that must not land in
    // shared dev/CI logs. To actually receive these in dev, set
    // RESEND_API_KEY.
    console.warn(
      `[auth-email] RESEND_API_KEY unset; would send to=${to} subject="${subject}" (body redacted)`,
    );
    return;
  }
  await resend.emails.send({ from: fromEmail, to, subject, text, html });
}

export async function sendVerificationEmail(
  to: string,
  url: string,
): Promise<void> {
  await send({
    to,
    subject: "Verify your Meli email",
    text: `Verify your email to activate your Meli account:\n\n${url}\n\nIf you didn't create this account, ignore this message.`,
    html: `<p>Verify your email to activate your Meli account:</p><p><a href="${url}">${url}</a></p><p style="color:#888">If you didn't create this account, ignore this message.</p>`,
  });
}

export async function sendResetPasswordEmail(
  to: string,
  url: string,
): Promise<void> {
  await send({
    to,
    subject: "Reset your Meli password",
    text: `Reset your Meli password using the link below:\n\n${url}\n\nThis link expires in one hour. If you didn't request a reset, ignore this message.`,
    html: `<p>Reset your Meli password using the link below:</p><p><a href="${url}">${url}</a></p><p style="color:#888">This link expires in one hour. If you didn't request a reset, ignore this message.</p>`,
  });
}
