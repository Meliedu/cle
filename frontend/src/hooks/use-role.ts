import { useUser } from "@clerk/nextjs";

type Role = "instructor" | "student";

export function useRole() {
  const { user, isLoaded } = useUser();
  const email = user?.primaryEmailAddress?.emailAddress;
  const role: Role = email?.endsWith("@ust.hk") ? "instructor" : "student";
  return {
    role,
    isInstructor: role === "instructor",
    isStudent: role === "student",
    isLoaded,
  } as const;
}
