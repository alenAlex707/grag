"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import {
  ArrowUp,
  DatabaseZap,
  FilePlus2,
  LoaderCircle,
  RotateCcw,
} from "lucide-react";

import { IngestionDialog } from "@/components/ingestion-dialog";
import { MessageList } from "@/components/message-list";
import { SettingsSidebar } from "@/components/settings-sidebar";
import { streamChat } from "@/lib/api";
import type { ChatMessage, RetrievalSettings } from "@/types";

const INITIAL_SETTINGS: RetrievalSettings = { topK: 5, graphHops: 2 };

export function ChatShell() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [settings, setSettings] = useState(INITIAL_SETTINGS);
  const [query, setQuery] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [ingestionOpen, setIngestionOpen] = useState(false);
  const scrollAnchor = useRef<HTMLDivElement>(null);
  const abortController = useRef<AbortController | undefined>(undefined);

  useEffect(() => {
    scrollAnchor.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    return () => abortController.current?.abort();
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedQuery = query.trim();
    if (!normalizedQuery || streaming) return;

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: normalizedQuery,
    };
    const assistantId = crypto.randomUUID();
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      pending: true,
    };

    setMessages((current) => [...current, userMessage, assistantMessage]);
    setQuery("");
    setStreaming(true);
    abortController.current = new AbortController();

    try {
      await streamChat(
        normalizedQuery,
        settings,
        (chunk) => {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId
                ? { ...message, content: message.content + chunk }
                : message,
            ),
          );
        },
        abortController.current.signal,
      );
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? { ...message, pending: false }
            : message,
        ),
      );
    } catch (cause) {
      const detail = cause instanceof Error ? cause.message : "The request failed.";
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                content: message.content || detail,
                pending: false,
                error: true,
              }
            : message,
        ),
      );
    } finally {
      setStreaming(false);
      abortController.current = undefined;
    }
  }

  return (
    <main className="flex min-h-screen flex-col bg-[#0e1012] text-zinc-100 md:h-screen md:flex-row md:overflow-hidden">
      <SettingsSidebar onChange={setSettings} settings={settings} />

      <section className="relative flex min-h-[70vh] min-w-0 flex-1 flex-col md:min-h-0">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_55%_-10%,rgba(190,242,100,0.055),transparent_35%)]" />
        <header className="relative z-10 flex h-18 shrink-0 items-center justify-between border-b border-white/8 px-5 sm:px-8">
          <div className="flex items-center gap-2.5">
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-lime-300 opacity-30" />
              <span className="relative inline-flex size-2 rounded-full bg-lime-300" />
            </span>
            <span className="font-mono text-[10px] font-medium tracking-[0.18em] text-zinc-500 uppercase">
              Local engine online
            </span>
          </div>
          <div className="flex items-center gap-2">
            {messages.length > 0 && (
              <button
                aria-label="Start a new conversation"
                className="rounded-lg p-2.5 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200"
                disabled={streaming}
                onClick={() => setMessages([])}
                type="button"
              >
                <RotateCcw className="size-4" />
              </button>
            )}
            <button
              className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.035] px-3.5 py-2.5 text-xs font-semibold text-zinc-300 transition hover:border-lime-300/25 hover:text-white"
              onClick={() => setIngestionOpen(true)}
              type="button"
            >
              <FilePlus2 className="size-4 text-lime-300" />
              <span className="hidden sm:inline">Add knowledge</span>
            </button>
          </div>
        </header>

        <div className="relative min-h-0 flex-1 overflow-y-auto">
          <MessageList messages={messages} />
          <div ref={scrollAnchor} />
        </div>

        <div className="relative z-10 shrink-0 px-4 pb-5 sm:px-8 sm:pb-7">
          <form
            className="mx-auto max-w-3xl rounded-2xl border border-white/10 bg-[#15181a]/95 p-2 shadow-[0_18px_60px_rgba(0,0,0,0.28)] backdrop-blur"
            onSubmit={handleSubmit}
          >
            <div className="flex items-end gap-2">
              <textarea
                aria-label="Ask Grag"
                className="max-h-40 min-h-12 flex-1 resize-none bg-transparent px-3 py-3 text-sm leading-6 text-zinc-100 outline-none placeholder:text-zinc-600"
                disabled={streaming}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
                placeholder="Ask a question across your knowledge…"
                rows={1}
                value={query}
              />
              <button
                aria-label="Send message"
                className="grid size-11 shrink-0 place-items-center rounded-xl bg-lime-300 text-[#10120f] transition hover:bg-lime-200 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-600"
                disabled={!query.trim() || streaming}
                type="submit"
              >
                {streaming ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : (
                  <ArrowUp className="size-4" strokeWidth={2.5} />
                )}
              </button>
            </div>
            <div className="flex items-center gap-1.5 px-3 pb-1 pt-2 text-[10px] text-zinc-700">
              <DatabaseZap className="size-3" />
              <span>Graph + vector context</span>
              <span className="ml-auto hidden sm:inline">Enter to send · Shift + Enter for a new line</span>
            </div>
          </form>
        </div>
      </section>

      <IngestionDialog
        onClose={() => setIngestionOpen(false)}
        open={ingestionOpen}
      />
    </main>
  );
}
