import { openDB, type IDBPDatabase } from "idb";
import type { Chunk, DocMeta, Thread } from "./types";

const DB_NAME = "marginalia-v1";
const VERSION = 1;

let dbp: Promise<IDBPDatabase> | null = null;
function db() {
  if (!dbp) {
    dbp = openDB(DB_NAME, VERSION, {
      upgrade(d) {
        d.createObjectStore("docs", { keyPath: "id" });
        d.createObjectStore("blobs"); // key = docId -> ArrayBuffer
        const cs = d.createObjectStore("chunks", { keyPath: "id" });
        cs.createIndex("docId", "docId");
        const es = d.createObjectStore("embeddings"); // key = chunkId -> Float32Array
        d.createObjectStore("threads", { keyPath: "id" });
        d.createObjectStore("headings"); // key = docId -> [{page,text}]
        d.createObjectStore("summaries"); // key = docId -> { summary, keyphrases }
      },
    });
  }
  return dbp;
}

export const store = {
  async listDocs(): Promise<DocMeta[]> {
    const d = await db();
    return (await d.getAll("docs")) as DocMeta[];
  },
  async getDoc(id: string): Promise<DocMeta | undefined> {
    return (await (await db()).get("docs", id)) as DocMeta | undefined;
  },
  async putDoc(meta: DocMeta) {
    await (await db()).put("docs", meta);
  },
  async deleteDoc(id: string) {
    const d = await db();
    const tx = d.transaction(["docs","blobs","chunks","embeddings","threads","headings","summaries"], "readwrite");
    await tx.objectStore("docs").delete(id);
    await tx.objectStore("blobs").delete(id);
    await tx.objectStore("headings").delete(id);
    await tx.objectStore("summaries").delete(id);
    const cs = tx.objectStore("chunks");
    const idx = cs.index("docId");
    let cur = await idx.openCursor(IDBKeyRange.only(id));
    const chunkIds: string[] = [];
    while (cur) { chunkIds.push(cur.value.id); await cur.delete(); cur = await cur.continue(); }
    const es = tx.objectStore("embeddings");
    for (const cid of chunkIds) await es.delete(cid);
    const ts = tx.objectStore("threads");
    let tcur = await ts.openCursor();
    while (tcur) {
      if ((tcur.value as Thread).docId === id) await tcur.delete();
      tcur = await tcur.continue();
    }
    await tx.done;
  },
  async putBlob(id: string, buf: ArrayBuffer) {
    await (await db()).put("blobs", buf, id);
  },
  async getBlob(id: string): Promise<ArrayBuffer | undefined> {
    return (await (await db()).get("blobs", id)) as ArrayBuffer | undefined;
  },
  async putChunks(chunks: Chunk[]) {
    const d = await db();
    const tx = d.transaction("chunks", "readwrite");
    for (const c of chunks) await tx.store.put(c);
    await tx.done;
  },
  async getChunks(docId: string): Promise<Chunk[]> {
    const d = await db();
    const idx = d.transaction("chunks").store.index("docId");
    return (await idx.getAll(IDBKeyRange.only(docId))) as Chunk[];
  },
  async putEmbedding(chunkId: string, vec: Float32Array) {
    await (await db()).put("embeddings", vec, chunkId);
  },
  async getEmbedding(chunkId: string): Promise<Float32Array | undefined> {
    return (await (await db()).get("embeddings", chunkId)) as Float32Array | undefined;
  },
  async getEmbeddingsFor(docId: string): Promise<Map<string, Float32Array>> {
    const d = await db();
    const map = new Map<string, Float32Array>();
    const tx = d.transaction("embeddings", "readonly");
    const store = tx.objectStore("embeddings");
    // Since chunkId is `${docId}:${idx}`, we can use a range scan
    let cursor = await store.openCursor(IDBKeyRange.bound(docId + ":", docId + ":\uffff"));
    while (cursor) {
      map.set(cursor.key as string, cursor.value as Float32Array);
      cursor = await cursor.continue();
    }
    return map;
  },
  async putHeadings(docId: string, headings: { page: number; text: string }[]) {
    await (await db()).put("headings", headings, docId);
  },
  async getHeadings(docId: string): Promise<{ page: number; text: string }[]> {
    return ((await (await db()).get("headings", docId)) as any) ?? [];
  },
  async putSummary(docId: string, payload: { summary: string[]; keyphrases: string[]; entities: string[] }) {
    await (await db()).put("summaries", payload, docId);
  },
  async getSummary(docId: string) {
    return (await (await db()).get("summaries", docId)) as { summary: string[]; keyphrases: string[]; entities: string[] } | undefined;
  },
  async listThreads(docId: string): Promise<Thread[]> {
    const all = (await (await db()).getAll("threads")) as Thread[];
    return all.filter((t) => t.docId === docId).sort((a,b)=>b.createdAt-a.createdAt);
  },
  async putThread(t: Thread) { await (await db()).put("threads", t); },
  async deleteThread(id: string) { await (await db()).delete("threads", id); },
};
