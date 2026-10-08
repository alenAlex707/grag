import { Bot, Network, UserRound } from "lucide-react";

import type { ChatMessage } from "@/types";

interface MessageListProps {
  messages: ChatMessage[];
}

export function MessageList({ messages }: MessageListProps) {
  if (messages.length === 0) {
    return (
      <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center px-6 text-center">
        <div className="relative mb-7 grid size-20 place-items-center rounded-3xl border border-lime-300/20 bg-lime-300/[0.06]">
          <div className="absolute inset-2 rounded-2xl border border-lime-300/10" />
          <Network className="size-8 text-lime-300" strokeWidth={1.5} />
        </div>
        <p className="mb-3 font-mono text-[11px] font-semibold tracking-[0.22em] text-lime-300 uppercase">
          Your connected knowledge
        </p>
        <h2 className="text-3xl font-semibold tracking-[-0.04em] text-zinc-100 sm:text-4xl">
          Ask beyond the keywords.
        </h2>
        <p className="mt-4 max-w-lg text-sm leading-6 text-zinc-500 sm:text-base">
          Grag follows relationships across your documents, then combines them
          with semantic evidence for grounded answers.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-8 px-5 py-10 sm:px-8">
      {messages.map((message) => (
        <article
          className={`flex gap-4 ${message.role === "user" ? "justify-end" : ""}`}
          key={message.id}
        >
          {message.role === "assistant" && (
            <div className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg border border-lime-300/20 bg-lime-300/[0.06] text-lime-300">
              <Bot className="size-4" />
            </div>
          )}
          <div
            className={
              message.role === "user"
                ? "max-w-[82%] rounded-2xl rounded-br-sm bg-zinc-100 px-5 py-3.5 text-sm leading-6 text-zinc-900"
                : `max-w-[86%] pt-1 text-sm leading-7 whitespace-pre-wrap sm:text-[15px] ${
                    message.error ? "text-red-300" : "text-zinc-300"
                  }`
            }
          >
            {message.content || <StreamingDots />}
          </div>
          {message.role === "user" && (
            <div className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg bg-white/5 text-zinc-400">
              <UserRound className="size-4" />
            </div>
          )}
        </article>
      ))}
    </div>
  );
}

function StreamingDots() {
  return (
    <span aria-label="Grag is thinking" className="flex h-6 items-center gap-1">
      {[0, 1, 2].map((index) => (
        <span
          className="stream-dot size-1.5 rounded-full bg-lime-300"
          key={index}
          style={{ animationDelay: `${index * 140}ms` }}
        />
      ))}
    </span>
  );
}
