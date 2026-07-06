"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { roleHomePath, useRole } from "@/hooks/use-role";

export default function DashboardRedirect() {
  const { role } = useRole();
  const router = useRouter();

  useEffect(() => {
    // `role` is non-null exactly when the role query has loaded (isLoaded).
    if (role !== null) {
      router.replace(roleHomePath(role));
    }
  }, [role, router]);

  return null;
}
