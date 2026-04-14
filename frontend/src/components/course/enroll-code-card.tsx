"use client";

import { useCallback, useState } from "react";
import { Copy, Check, KeyRound } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface EnrollCodeCardProps {
  readonly enrollCode: string;
}

export function EnrollCodeCard({ enrollCode }: EnrollCodeCardProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(enrollCode);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard denied — nothing we can do silently.
    }
  }, [enrollCode]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="size-4" />
          Enrollment code
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm text-[var(--color-text-muted)]">
            Share this code with your students so they can join.
          </p>
          <p className="mt-2 font-mono text-2xl font-semibold tracking-[0.3em] text-[var(--color-text)]">
            {enrollCode}
          </p>
        </div>
        <Button variant="outline" onClick={handleCopy}>
          {copied ? (
            <>
              <Check className="size-4" />
              Copied
            </>
          ) : (
            <>
              <Copy className="size-4" />
              Copy code
            </>
          )}
        </Button>
      </CardContent>
    </Card>
  );
}
