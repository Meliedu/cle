"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useRole } from "@/hooks/use-role";

export default function DashboardRedirect() {
  const { role, isLoaded } = useRole();
  const router = useRouter();

  useEffect(() => {
    if (isLoaded) {
      router.replace(
        role === "instructor" ? "/teacher/dashboard" : "/student/dashboard"
      );
    }
  }, [isLoaded, role, router]);

  return null;
}
