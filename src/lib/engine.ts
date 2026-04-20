import type { Chunk, QueryHit, RetrievalMode } from "./types";
import { BM25 } from "./bm25";
import { tokenize, expandQueryTerms } from "./text";
import { cosine, embedTexts } from "./embedClient";

// In-memory per-doc index. Built lazily after load.
export interface DocIndex {
  docId: string;
  chunks: Chunk[];
  bm25: BM25;
  embeddings?: Map<string, Float32Array>;
}

const indexes = new Map<string, DocIndex>();

export function buildIndex(docId: string, chunks: Chunk[], embeddings?: Map<string, Float32Array>): DocIndex {
  const bm = new BM25();
  for (const c of chunks) bm.add(c.id, c.tokens);
  bm.finalize();
  const idx: DocIndex = { docId, chunks, bm25: bm, embeddings };
  indexes.set(docId, idx);
  return idx;
}

export function getIndex(docId: string) { return indexes.get(docId); }
export function dropIndex(docId: string) { indexes.delete(docId); }

function minMax(vals: number[]): { min: number; max: number } {
  let mn = Infinity, mx = -Infinity;
  for (const v of vals) { if (v < mn) mn = v; if (v > mx) mx = v; }
  return { min: mn, max: mx };
}

export async function query(
  docId: string,
  q: string,
  mode: RetrievalMode = "hybrid",
  topK = 8
): Promise<QueryHit[]> {
  const idx = indexes.get(docId);
  if (!idx) return [];
  const stems = tokenize(q);
  const terms = expandQueryTerms(stems);

  // Lexical pass
  const lex = idx.bm25.search(q, terms, 80);
  const lexMap = new Map(lex.map((r) => [r.id, r]));

  // Semantic pass
  let semMap = new Map<string, number>();
  if ((mode === "semantic" || mode === "hybrid") && idx.embeddings && idx.embeddings.size) {
    const [qv] = await embedTexts([q]);
    for (const c of idx.chunks) {
      const v = idx.embeddings.get(c.id);
      if (!v) continue;
      semMap.set(c.id, cosine(qv, v));
    }
  }

  // Build candidate set
  const candidates = new Set<string>();
  for (const r of lex) candidates.add(r.id);
  if (semMap.size) {
    // top semantic chunks too
    const sorted = Array.from(semMap.entries()).sort((a, b) => b[1] - a[1]).slice(0, 80);
    for (const [id] of sorted) candidates.add(id);
  }
  if (!candidates.size) return [];

  const lexVals = Array.from(candidates).map((id) => lexMap.get(id)?.score ?? 0);
  const semVals = Array.from(candidates).map((id) => semMap.get(id) ?? 0);
  const lexN = minMax(lexVals);
  const semN = minMax(semVals);
  const lexRange = lexN.max - lexN.min;
  const semRange = semN.max - semN.min;

  const wLex = mode === "lexical" ? 1 : mode === "semantic" ? 0 : 0.45;
  const wSem = mode === "lexical" ? 0 : mode === "semantic" ? 1 : 0.55;

  const out: QueryHit[] = [];
  for (const id of candidates) {
    const c = idx.chunks.find((x) => x.id === id);
    if (!c) continue;
    const lexS = lexMap.get(id)?.score ?? 0;
    const semS = semMap.get(id) ?? 0;
    const lexNorm = lexRange === 0 ? (lexS > 0 ? 1 : 0) : (lexS - lexN.min) / lexRange;
    const semNorm = semRange === 0 ? (semS > 0 ? 1 : 0) : (semS - semN.min) / semRange;
    const score = wLex * lexNorm + wSem * semNorm;
    const matched = Array.from(lexMap.get(id)?.matched ?? []);
    out.push({ chunk: c, score, bm25: lexS, semantic: semS, matchedTerms: matched });
  }
  out.sort((a, b) => b.score - a.score);
  return out.slice(0, topK);
}
