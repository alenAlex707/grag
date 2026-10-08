import type { IngestionResult, RetrievalSettings } from "@/types";

const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

function errorMessage(payload: unknown, fallback: string): string {
  if (
    typeof payload === "object" &&
    payload !== null &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  return fallback;
}

export async function streamChat(
  query: string,
  settings: RetrievalSettings,
  onChunk: (chunk: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_URL}/api/v1/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      top_k: settings.topK,
      graph_hops: settings.graphHops,
    }),
    signal,
  });

  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    throw new Error(errorMessage(payload, "Grag could not start a response."));
  }
  if (!response.body) {
    throw new Error("The response stream is unavailable in this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      const remainder = decoder.decode();
      if (remainder) onChunk(remainder);
      break;
    }
    onChunk(decoder.decode(value, { stream: true }));
  }
}

export async function ingestDocument(input: {
  text?: string;
  file?: File;
}): Promise<IngestionResult> {
  const form = new FormData();
  if (input.text) form.append("text", input.text);
  if (input.file) form.append("file", input.file);

  const response = await fetch(`${API_URL}/api/v1/ingest`, {
    method: "POST",
    body: form,
  });
  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(errorMessage(payload, "The document could not be ingested."));
  }
  return payload as IngestionResult;
}
