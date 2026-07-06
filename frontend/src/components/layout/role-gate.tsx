"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { RoleLoadError } from "@/components/layout/role-load-error";
import { useRole } from "@/hooks/use-role";

interface RoleGateProps {
  readonly allow: "instructor" | "student";
  readonly children: React.ReactNode;
}

/** UI-lane guard only — data access is enforced by the backend on every endpoint. */
export function RoleGate({ allow, children }: RoleGateProps) {
  const { role, isLoaded, isError } = useRole();
  const router = useRouter();

  useEffect(() => {
    if (isLoaded && role !== allow) {
      router.replace(
        role === "instructor" ? "/teacher/dashboard" : "/student/dashboard"
      );
    }
  }, [isLoaded, role, allow, router]);

  if (isError && !isLoaded) return <RoleLoadError />;
  if (!isLoaded || role !== allow) return null;
  return <>{children}</>;
}
