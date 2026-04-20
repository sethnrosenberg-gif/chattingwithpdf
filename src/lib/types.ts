export interface DocMeta {
  id: string;
  name: string;
  pages: number;
  addedAt: number;
  size: number;
  hasEmbeddings: boolean;
}

export interface Chunk {
  id: string;          // `${docId}:${idx}`
  docId: string;
  idx: number;
  page: number;        // 1-based
  heading?: string;
  text: string;
  // Geometry of the chunk on its page (normalized 0..1 in pdf coords)
  bbox?: { x: number; y: number; w: number; h: number };
  // Token-level info for BM25
  tokens: string[];
}

export interface QueryHit {
  chunk: Chunk;
  score: number;
  bm25: number;
  semantic: number;
  matchedTerms: string[];
}

export interface Thread {
  id: string;
  docId: string;
  createdAt: number;
  messages: ThreadMessage[];
}

export interface ThreadMessage {
  id: string;
  role: "user" | "answer";
  text: string;
  hits?: QueryHit[];
  at: number;
  pinned?: boolean;
}

export type RetrievalMode = "lexical" | "semantic" | "hybrid";
