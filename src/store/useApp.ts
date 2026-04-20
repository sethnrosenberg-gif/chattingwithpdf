import { create } from "zustand";
import type { Chunk, DocMeta, QueryHit, RetrievalMode, Thread, ThreadMessage } from "@/lib/types";
import { store } from "@/lib/store";
import { buildIndex, dropIndex, getIndex, query } from "@/lib/engine";
import { parsePdf, chunkPages } from "@/lib/pdf";
import { embedTexts, warmupEmbedder } from "@/lib/embedClient";
import { textRankSummary, rakeKeyphrases, extractEntities } from "@/lib/summarize";

export interface CitationTarget {
  page: number;
  text: string;
  chunkId: string;
  at: number; // timestamp to retrigger highlight
}

interface AppState {
  docs: DocMeta[];
  activeDocId: string | null;
  loading: boolean;
  ingestStatus: { docId: string; pct: number; label: string } | null;
  retrievalMode: RetrievalMode;
  semanticReady: boolean;

  headings: { page: number; text: string }[];
  summary: string[];
  keyphrases: string[];
  entities: string[];

  threads: Thread[];
  activeThread: Thread | null;

  citation: CitationTarget | null;

  // actions
  init: () => Promise<void>;
  setActive: (id: string) => Promise<void>;
  ingestFile: (file: File, opts?: { embed?: boolean }) => Promise<string>;
  removeDoc: (id: string) => Promise<void>;
  setMode: (m: RetrievalMode) => void;
  enableSemantic: () => Promise<void>;
  ask: (q: string) => Promise<QueryHit[] | null>;
  newThread: () => void;
  pinMessage: (id: string) => Promise<void>;
  jumpToCitation: (page: number, text: string, chunkId: string) => void;
  exportThread: () => string;
}

export const useApp = create<AppState>((set, get) => ({
  docs: [],
  activeDocId: null,
  loading: false,
  ingestStatus: null,
  retrievalMode: "hybrid",
  semanticReady: false,
  headings: [],
  summary: [],
  keyphrases: [],
  entities: [],
  threads: [],
  activeThread: null,
  citation: null,

  init: async () => {
    const docs = await store.listDocs();
    set({ docs });
    if (docs.length) await get().setActive(docs[0].id);
  },

  setActive: async (id) => {
    set({ loading: true, activeDocId: id });
    let idx = getIndex(id);
    if (!idx) {
      const chunks = await store.getChunks(id);
      const embeddings = await store.getEmbeddingsFor(id);
      idx = buildIndex(id, chunks, embeddings.size ? embeddings : undefined);
    }
    const headings = await store.getHeadings(id);
    let summary: string[] = [];
    let keyphrases: string[] = [];
    let entities: string[] = [];
    const cached = await store.getSummary(id);
    if (cached) {
      summary = cached.summary;
      keyphrases = cached.keyphrases;
      entities = cached.entities ?? [];
    } else {
      const sampleChunks = idx.chunks.length > 200 
        ? [...idx.chunks.slice(0, 100), ...idx.chunks.slice(-100)] 
        : idx.chunks;
      const sampleText = sampleChunks.map((c) => c.text).join(" ");
      summary = textRankSummary(sampleText, 6);
      keyphrases = rakeKeyphrases(sampleText, 12);
      entities = extractEntities(sampleText, 12);
      await store.putSummary(id, { summary, keyphrases, entities });
    }
    const threads = await store.listThreads(id);
    set({
      loading: false,
      headings,
      summary,
      keyphrases,
      entities,
      threads,
      activeThread: threads[0] ?? null,
      semanticReady: !!idx.embeddings,
      citation: null,
    });
  },

  ingestFile: async (file, opts) => {
    const id = crypto.randomUUID();
    set({ ingestStatus: { docId: id, pct: 0, label: "Reading PDF…" } });
    const { pages, headings, bytes } = await parsePdf(file, (pct, label) =>
      set({ ingestStatus: { docId: id, pct: pct * 0.4, label } })
    );
    const { chunks } = chunkPages(id, pages, headings);
    const meta: DocMeta = {
      id, name: file.name.replace(/\.pdf$/i, ""), pages: pages.length,
      addedAt: Date.now(), size: file.size, hasEmbeddings: false,
    };
    await store.putDoc(meta);
    await store.putBlob(id, bytes);
    await store.putChunks(chunks);
    await store.putHeadings(id, headings);

    await generateAndCacheSummary(id, chunks);

    set({ ingestStatus: { docId: id, pct: 0.5, label: "Indexing lexical…" } });
    buildIndex(id, chunks);

    if (opts?.embed) {
      try {
        await warmupEmbedder((label) => set({ ingestStatus: { docId: id, pct: 0.55, label } }));
        const vectors = await embedTexts(
          chunks.map((c) => c.text),
          (done, total) => set({ ingestStatus: { docId: id, pct: 0.6 + 0.35 * (done / total), label: `Embedding ${done}/${total}` } })
        );
        for (let i = 0; i < chunks.length; i++) {
          await store.putEmbedding(chunks[i].id, vectors[i]);
        }
        meta.hasEmbeddings = true;
        await store.putDoc(meta);
      } catch (e) {
        console.warn("Embedding skipped:", e);
      }
    }

    set({
      docs: await store.listDocs(),
      ingestStatus: { docId: id, pct: 1, label: "Done" },
    });
    setTimeout(() => set({ ingestStatus: null }), 600);
    await get().setActive(id);
    return id;
  },

  removeDoc: async (id) => {
    await store.deleteDoc(id);
    dropIndex(id);
    const docs = await store.listDocs();
    const next = docs[0]?.id ?? null;
    set({ docs, activeDocId: next });
    if (next) await get().setActive(next);
    else set({ headings: [], summary: [], keyphrases: [], entities: [], threads: [], activeThread: null });
  },

  setMode: (m) => set({ retrievalMode: m }),

  enableSemantic: async () => {
    const id = get().activeDocId;
    if (!id) return;
    const chunks = await store.getChunks(id);
    set({ ingestStatus: { docId: id, pct: 0, label: "Loading semantic model…" } });
    await warmupEmbedder((label) => set({ ingestStatus: { docId: id, pct: 0.05, label } }));
    const vectors = await embedTexts(
      chunks.map((c) => c.text),
      (done, total) => set({ ingestStatus: { docId: id, pct: 0.1 + 0.85 * (done / total), label: `Embedding ${done}/${total}` } })
    );
    for (let i = 0; i < chunks.length; i++) {
      await store.putEmbedding(chunks[i].id, vectors[i]);
    }
    const meta = await store.getDoc(id);
    if (meta) { meta.hasEmbeddings = true; await store.putDoc(meta); }
    const map = new Map<string, Float32Array>();
    chunks.forEach((c, i) => map.set(c.id, vectors[i]));
    buildIndex(id, chunks, map);
    set({
      semanticReady: true,
      docs: await store.listDocs(),
      ingestStatus: null,
    });
  },

  ask: async (q) => {
    const docId = get().activeDocId;
    if (!docId || !q.trim()) return null;
    const mode = get().retrievalMode;
    const effective = mode === "lexical" || !get().semanticReady ? "lexical" : mode;
    const hits = await query(docId, q, effective as RetrievalMode, 6);
    let thread = get().activeThread;
    if (!thread) {
      thread = { id: crypto.randomUUID(), docId, createdAt: Date.now(), messages: [] };
    }
    const userMsg: ThreadMessage = { id: crypto.randomUUID(), role: "user", text: q, at: Date.now() };
    const ansMsg: ThreadMessage = { id: crypto.randomUUID(), role: "answer", text: hits.length ? "" : "No matching passages found.", hits, at: Date.now() };
    thread = { ...thread, messages: [...thread.messages, userMsg, ansMsg] };
    await store.putThread(thread);
    const threads = await store.listThreads(docId);
    set({ activeThread: thread, threads });
    return hits;
  },

  newThread: () => {
    const docId = get().activeDocId;
    if (!docId) return;
    const t: Thread = { id: crypto.randomUUID(), docId, createdAt: Date.now(), messages: [] };
    set({ activeThread: t });
  },

  pinMessage: async (id) => {
    const t = get().activeThread;
    if (!t) return;
    const next = { ...t, messages: t.messages.map((m) => m.id === id ? { ...m, pinned: !m.pinned } : m) };
    await store.putThread(next);
    set({ activeThread: next });
  },

  jumpToCitation: (page, text, chunkId) => {
    set({ citation: { page, text, chunkId, at: Date.now() } });
  },

  exportThread: () => {
    const t = get().activeThread;
    if (!t) return "";
    const lines: string[] = [`# Marginalia thread — ${new Date(t.createdAt).toISOString()}`, ""];
    for (const m of t.messages) {
      if (m.role === "user") lines.push(`## Q: ${m.text}`);
      else {
        lines.push(`**Findings:**`);
        for (const h of m.hits ?? []) {
          lines.push(`- p.${h.chunk.page}${h.chunk.heading ? ` · ${h.chunk.heading}` : ""} — "${h.chunk.text}"`);
        }
        lines.push("");
      }
    }
    return lines.join("\n");
  },
}));
