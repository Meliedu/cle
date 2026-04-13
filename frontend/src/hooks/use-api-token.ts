import { useAuth } from "@clerk/nextjs";
import { useCallback } from "react";

export function useApiToken(): () => Promise<string | null> {
  const { getToken } = useAuth();

  return useCallback(async () => {
    const token = await getToken({ template: "backend" });
    return token;
  }, [getToken]);
}
