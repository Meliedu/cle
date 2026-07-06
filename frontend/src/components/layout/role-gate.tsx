"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { roleHomePath, useRole } from "@/hooks/use-role";

interface RoleGateProps {
  readonly allow: "instructor" | "student";
  readonly children: React.ReactNode;
}

/**
 * UI-lane guard only — data access is enforced by the backend on every
 * endpoint. Only mounted inside AppShell, which blocks until the role is
 * loaded or errored — this gate only decides lane membership.
 */
export function RoleGate({ allow, children }: RoleGateProps) {
  const { role } = useRole();
  const router = useRouter();

  useEffect(() => {
    if (role !== null && role !== allow) {
      router.replace(roleHomePath(role));
    }
  }, [role, allow, router]);

  if (role !== allow) return null;
  return <>{children}</>;
}
