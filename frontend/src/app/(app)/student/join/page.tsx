import { JoinFunnel } from "./join-funnel";

/**
 * `/student/join` — the student join funnel entry (S003 code entry onward).
 * Wrapped by the student `AppShell` + `RoleGate` from the segment layout.
 */
export default function StudentJoinPage() {
  return <JoinFunnel />;
}
