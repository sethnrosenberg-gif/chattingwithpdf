// Singleton wrapper around the embedding worker.
// @ts-ignore
import EmbedWorker from "@/workers/embed.worker.ts?worker";

let worker: Worker | null = null;
let nextId = 1;
const handlers = new Map<number, (msg: any) => void>();

function ensure(): Worker {
  if (worker) return worker;
  worker = new EmbedWorker();
  worker.onmessage = (ev) => {
    const id = ev.data?.id;
    const h = handlers.get(id);
    if (!h) return;
    if (ev.data.type === "progress") { h(ev.data); return; }
    handlers.delete(id);
    h(ev.data);
  };
  return worker;
}

export function warmupEmbedder(onProgress?: (label: string) => void): Promise<void> {
  const w = ensure();
  return new Promise((resolve, reject) => {
    const id = nextId++;
    handlers.set(id, (m) => {
      if (m.ok) resolve();
      else reject(new Error(m.error || "warmup failed"));
    });
    onProgress?.("Loading semantic model (≈25MB, one-time, then offline)…");
    w.postMessage({ id, type: "warmup" });
  });
}

export function embedTexts(texts: string[], onProgress?: (done: number, total: number) => void): Promise<Float32Array[]> {
  const w = ensure();
  return new Promise((resolve, reject) => {
    const id = nextId++;
    handlers.set(id, (m) => {
      if (m.type === "progress") { onProgress?.(m.done, m.total); return; }
      if (m.ok) resolve(m.vectors as Float32Array[]);
      else reject(new Error(m.error || "embed failed"));
    });
    w.postMessage({ id, type: "embed", payload: { texts } });
  });
}

export function cosine(a: Float32Array, b: Float32Array): number {
  let s = 0;
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) s += a[i] * b[i];
  return s; // both normalized
}
