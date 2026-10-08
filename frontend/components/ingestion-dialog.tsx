"use client";

import { useRef, useState } from "react";
import {
  CheckCircle2,
  FileText,
  LoaderCircle,
  UploadCloud,
  X,
} from "lucide-react";

import { ingestDocument } from "@/lib/api";
import type { IngestionResult } from "@/types";

interface IngestionDialogProps {
  open: boolean;
  onClose: () => void;
}

type InputMode = "text" | "file";

export function IngestionDialog({ open, onClose }: IngestionDialogProps) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<InputMode>("text");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<IngestionResult>();

  if (!open) return null;

  const canSubmit = mode === "text" ? text.trim().length > 0 : Boolean(file);

  async function handleSubmit() {
    if (!canSubmit || loading) return;
    setLoading(true);
    setError("");
    setResult(undefined);
    try {
      const nextResult = await ingestDocument(
        mode === "text" ? { text: text.trim() } : { file },
      );
      setResult(nextResult);
      setText("");
      setFile(undefined);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Ingestion failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      aria-modal="true"
      className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target && !loading) onClose();
      }}
      role="dialog"
    >
      <div className="w-full max-w-xl overflow-hidden rounded-2xl border border-white/10 bg-[#111416] shadow-2xl shadow-black/50">
        <header className="flex items-start justify-between border-b border-white/8 px-6 py-5">
          <div>
            <p className="font-mono text-[10px] tracking-[0.2em] text-lime-300 uppercase">
              Expand the graph
            </p>
            <h2 className="mt-1 text-xl font-semibold text-zinc-100">
              Add knowledge
            </h2>
          </div>
          <button
            aria-label="Close ingestion dialog"
            className="rounded-lg p-2 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200"
            disabled={loading}
            onClick={onClose}
            type="button"
          >
            <X className="size-5" />
          </button>
        </header>

        <div className="p-6">
          <div className="mb-5 flex rounded-lg bg-black/30 p-1">
            {(["text", "file"] as const).map((item) => (
              <button
                className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition ${
                  mode === item
                    ? "bg-white/8 text-white shadow-sm"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
                key={item}
                onClick={() => {
                  setMode(item);
                  setError("");
                  setResult(undefined);
                }}
                type="button"
              >
                {item === "text" ? "Paste text" : "Upload file"}
              </button>
            ))}
          </div>

          {mode === "text" ? (
            <textarea
              autoFocus
              className="min-h-52 w-full resize-y rounded-xl border border-white/10 bg-black/20 p-4 text-sm leading-6 text-zinc-200 outline-none transition placeholder:text-zinc-700 focus:border-lime-300/40 focus:ring-2 focus:ring-lime-300/5"
              onChange={(event) => setText(event.target.value)}
              placeholder="Paste notes, documentation, or any source material…"
              value={text}
            />
          ) : (
            <button
              className="flex min-h-52 w-full flex-col items-center justify-center rounded-xl border border-dashed border-white/12 bg-black/15 p-6 text-center transition hover:border-lime-300/30 hover:bg-lime-300/[0.02]"
              onClick={() => fileInput.current?.click()}
              type="button"
            >
              {file ? (
                <>
                  <FileText className="mb-3 size-8 text-lime-300" />
                  <span className="text-sm font-medium text-zinc-200">{file.name}</span>
                  <span className="mt-1 text-xs text-zinc-600">
                    {(file.size / 1024).toFixed(1)} KB · click to replace
                  </span>
                </>
              ) : (
                <>
                  <UploadCloud className="mb-3 size-8 text-zinc-500" />
                  <span className="text-sm font-medium text-zinc-300">
                    Choose a text document
                  </span>
                  <span className="mt-1 text-xs text-zinc-600">
                    UTF-8 .txt or .md · up to 10 MB
                  </span>
                </>
              )}
              <input
                accept=".txt,.md,text/plain,text/markdown"
                className="hidden"
                onChange={(event) => setFile(event.target.files?.[0])}
                ref={fileInput}
                type="file"
              />
            </button>
          )}

          {error && (
            <p className="mt-4 rounded-lg border border-red-400/15 bg-red-400/5 px-4 py-3 text-sm text-red-300">
              {error}
            </p>
          )}
          {result && (
            <div className="mt-4 flex items-start gap-3 rounded-lg border border-lime-300/15 bg-lime-300/5 px-4 py-3">
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-lime-300" />
              <p className="text-sm leading-5 text-zinc-300">
                Added {result.chunk_count} chunk{result.chunk_count === 1 ? "" : "s"}
                {" and "}
                {result.triple_count} graph relationship
                {result.triple_count === 1 ? "" : "s"}.
              </p>
            </div>
          )}

          <div className="mt-6 flex justify-end gap-3">
            <button
              className="rounded-lg px-4 py-2.5 text-sm font-medium text-zinc-500 transition hover:text-zinc-200"
              disabled={loading}
              onClick={onClose}
              type="button"
            >
              {result ? "Done" : "Cancel"}
            </button>
            {!result && (
              <button
                className="flex min-w-32 items-center justify-center gap-2 rounded-lg bg-lime-300 px-4 py-2.5 text-sm font-semibold text-[#10120f] transition hover:bg-lime-200 disabled:cursor-not-allowed disabled:opacity-40"
                disabled={!canSubmit || loading}
                onClick={handleSubmit}
                type="button"
              >
                {loading && <LoaderCircle className="size-4 animate-spin" />}
                {loading ? "Ingesting…" : "Add to Grag"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
