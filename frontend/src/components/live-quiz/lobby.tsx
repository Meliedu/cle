"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Users, Copy, Check, Loader2, Radio } from "lucide-react";
import { useState, useCallback } from "react";
import type { LiveStatus } from "@/hooks/use-live-quiz";

interface LobbyProps {
  readonly joinCode: string;
  readonly participantCount: number;
  readonly isHost: boolean;
  readonly status: LiveStatus;
  readonly onStart: () => void;
}

export function Lobby({
  joinCode,
  participantCount,
  isHost,
  status,
  onStart,
}: LobbyProps) {
  const [copied, setCopied] = useState(false);

  const copyCode = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(joinCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API not available
    }
  }, [joinCode]);

  const isConnected = status === "connected";

  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-6">
      {/* Connection status */}
      <Badge
        variant="outline"
        className={
          isConnected
            ? "border-[var(--color-success)] text-[var(--color-success)]"
            : "border-[var(--color-warning)] text-[var(--color-warning)]"
        }
      >
        <Radio className="size-3" />
        {isConnected ? "Connected" : "Connecting..."}
      </Badge>

      {/* Join code card */}
      <Card className="w-full">
        <CardHeader className="text-center">
          <CardTitle className="text-sm font-medium text-[var(--color-text-muted)]">
            Join Code
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col items-center gap-4">
          <button
            onClick={copyCode}
            className="group flex items-center gap-3 rounded-[var(--radius-xl)] bg-[var(--color-surface-hover)] px-8 py-4 transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-primary-light)]"
          >
            <span className="font-mono text-4xl font-bold tracking-[0.3em] text-[var(--color-text)]">
              {joinCode}
            </span>
            {copied ? (
              <Check className="size-5 text-[var(--color-success)]" />
            ) : (
              <Copy className="size-5 text-[var(--color-text-muted)] transition-colors group-hover:text-[var(--color-primary)]" />
            )}
          </button>
          <p className="text-xs text-[var(--color-text-muted)]">
            Share this code with your students
          </p>
        </CardContent>
      </Card>

      {/* Participant count */}
      <Card className="w-full">
        <CardContent className="flex items-center justify-center gap-3 py-6">
          <div className="flex size-10 items-center justify-center rounded-full bg-[var(--color-primary-light)]">
            <Users className="size-5 text-[var(--color-primary)]" />
          </div>
          <div>
            <p className="text-2xl font-bold text-[var(--color-text)]">
              {participantCount}
            </p>
            <p className="text-xs text-[var(--color-text-muted)]">
              {participantCount === 1 ? "participant" : "participants"} joined
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Action area */}
      {isHost ? (
        <Button
          size="lg"
          className="w-full"
          onClick={onStart}
          disabled={!isConnected}
        >
          Start Quiz
        </Button>
      ) : (
        <Card className="w-full">
          <CardContent className="flex flex-col items-center gap-2 py-6">
            <Loader2 className="size-6 animate-spin text-[var(--color-primary)]" />
            <p className="text-sm font-medium text-[var(--color-text)]">
              Waiting for host to start...
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
