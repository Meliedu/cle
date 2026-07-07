import { JoinFunnel } from "./join-funnel";

interface StudentJoinPageProps {
  /** Next.js 16 passes `searchParams` as a Promise in server components. */
  readonly searchParams: Promise<{ code?: string | string[] }>;
}

/**
 * `/student/join` — the student join funnel entry (S003 code entry onward).
 * Wrapped by the student `AppShell` + `RoleGate` from the segment layout. A
 * `?code=XXXX` deep link (emailed invite) prefills the code field on S003.
 */
export default async function StudentJoinPage({
  searchParams,
}: StudentJoinPageProps) {
  const { code } = await searchParams;
  const initialCode = Array.isArray(code) ? code[0] : code;
  return <JoinFunnel initialCode={initialCode} />;
}
