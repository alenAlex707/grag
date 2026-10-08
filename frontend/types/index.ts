export type MessageRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  pending?: boolean;
  error?: boolean;
}

export interface RetrievalSettings {
  topK: number;
  graphHops: number;
}

export interface IngestionResult {
  document_ids: string[];
  document_count: number;
  chunk_count: number;
  triple_count: number;
}
