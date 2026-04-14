"use client";

import { useCallback, useState } from "react";
import { Loader2, Link2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useStartCanvasOAuth } from "@/hooks/use-canvas";

interface CanvasConnectButtonProps {
  readonly label?: string;
  readonly variant?: "default" | "outline";
  readonly className?: string;
}

export function CanvasConnectButton({
  label = "Connect Canvas",
  variant = "default",
  className,
}: CanvasConnectButtonProps) {
  const startOAuth = useStartCanvasOAuth();
  const [redirecting, setRedirecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClick = useCallback(async () => {
    setError(null);
    try {
      const { authorize_url } = await startOAuth.mutateAsync();
      setRedirecting(true);
      window.location.assign(authorize_url);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to start Canvas connection";
      setError(message);
    }
  }, [startOAuth]);

  const disabled = startOAuth.isPending || redirecting;

  return (
    <div className={className}>
      <Button variant={variant} onClick={handleClick} disabled={disabled}>
        {disabled ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <Link2 className="size-4" />
        )}
        {redirecting ? "Redirecting…" : label}
      </Button>
      {error && (
        <p className="mt-2 text-xs text-[var(--color-error)]">{error}</p>
      )}
    </div>
  );
}
