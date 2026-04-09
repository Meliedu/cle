"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { Mic, Square, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

type RecordingState = "idle" | "recording" | "processing";

interface RecorderProps {
  readonly onRecordingComplete: (blob: Blob) => void;
  readonly isProcessing?: boolean;
}

export function Recorder({
  onRecordingComplete,
  isProcessing = false,
}: RecorderProps) {
  const [state, setState] = useState<RecordingState>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const currentState: RecordingState = isProcessing ? "processing" : state;

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (mediaRecorderRef.current?.state === "recording") {
        mediaRecorderRef.current.stop();
      }
    };
  }, []);

  const startRecording = useCallback(async () => {
    setError(null);
    chunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
      });

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported("audio/webm")
          ? "audio/webm"
          : "audio/mp4",
      });

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current = [...chunksRef.current, event.data];
        }
      };

      mediaRecorder.onstop = () => {
        // Stop all tracks to release the microphone
        stream.getTracks().forEach((track) => track.stop());

        const blob = new Blob(chunksRef.current, {
          type: mediaRecorder.mimeType,
        });
        onRecordingComplete(blob);
        setState("idle");
      };

      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.start(250); // Collect data every 250ms
      setState("recording");
      setElapsed(0);

      timerRef.current = setInterval(() => {
        setElapsed((prev) => prev + 1);
      }, 1000);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Microphone access denied";
      setError(message);
    }
  }, [onRecordingComplete]);

  const stopRecording = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
  }, []);

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-4 py-6">
        {/* Recording indicator */}
        <div className="relative flex items-center justify-center">
          <div
            className="flex size-20 items-center justify-center rounded-full transition-all duration-[var(--duration-normal)]"
            style={{
              backgroundColor:
                currentState === "recording"
                  ? "var(--color-error-light)"
                  : currentState === "processing"
                    ? "var(--color-primary-light)"
                    : "var(--color-surface-hover)",
            }}
          >
            {currentState === "recording" && (
              <span
                className="absolute inset-0 animate-ping rounded-full opacity-30"
                style={{
                  backgroundColor: "var(--color-error-light)",
                }}
              />
            )}
            {currentState === "processing" ? (
              <Loader2
                className="size-8 animate-spin"
                style={{ color: "var(--color-primary)" }}
              />
            ) : currentState === "recording" ? (
              <Mic
                className="relative size-8"
                style={{ color: "var(--color-error)" }}
              />
            ) : (
              <Mic
                className="size-8"
                style={{ color: "var(--color-text-muted)" }}
              />
            )}
          </div>
        </div>

        {/* Timer */}
        {currentState === "recording" && (
          <p
            className="font-mono text-lg font-semibold tabular-nums"
            style={{ color: "var(--color-error)" }}
          >
            {formatTime(elapsed)}
          </p>
        )}

        {/* Status text */}
        <p
          className="text-sm"
          style={{ color: "var(--color-text-muted)" }}
        >
          {currentState === "idle" && "Tap the button to start recording"}
          {currentState === "recording" && "Recording... Tap stop when done"}
          {currentState === "processing" && "Analyzing your pronunciation..."}
        </p>

        {/* Controls */}
        <div className="flex gap-3">
          {currentState === "idle" && (
            <Button onClick={startRecording} disabled={isProcessing}>
              <Mic className="size-4" />
              Start Recording
            </Button>
          )}
          {currentState === "recording" && (
            <Button
              variant="outline"
              onClick={stopRecording}
              style={{
                borderColor: "var(--color-error)",
                color: "var(--color-error)",
              }}
            >
              <Square className="size-4" />
              Stop Recording
            </Button>
          )}
        </div>

        {/* Error message */}
        {error && (
          <p
            className="text-center text-sm"
            style={{ color: "var(--color-error)" }}
          >
            {error}
          </p>
        )}
      </CardContent>

    </Card>
  );
}
