// Embeddings worker — uses Transformers.js with MiniLM. Loads model from CDN on first use,
// then caches in browser cache. Once cached, fully offline.
// Note: We accept a one-time model fetch as the practical price of "no LLM" semantic search.
// All inference runs locally.

import { pipeline, env } from "@huggingface/transformers";

env.allowLocalModels = false;
env.useBrowserCache = true;

let extractor: any | null = null;
async function getExtractor() {
  if (!extractor) {
    extractor = await pipeline("feature-extraction", "Xenova/all-MiniLM-L6-v2", { dtype: "fp32" });
  }
  return extractor;
}

self.onmessage = async (ev: MessageEvent) => {
  const { id, type, payload } = ev.data ?? {};
  try {
    if (type === "warmup") {
      await getExtractor();
      (self as any).postMessage({ id, ok: true });
      return;
    }
    if (type === "embed") {
      const ex = await getExtractor();
      const texts: string[] = payload.texts;
      const out: Float32Array[] = [];
      // Process in small batches to stream progress
      const BATCH = 8;
      for (let i = 0; i < texts.length; i += BATCH) {
        const slice = texts.slice(i, i + BATCH);
        const res = await ex(slice, { pooling: "mean", normalize: true });
        // res.data is Float32Array of shape [n, dim]
        const dim = res.dims[res.dims.length - 1];
        const flat = res.data as Float32Array;
        for (let j = 0; j < slice.length; j++) {
          out.push(flat.slice(j * dim, (j + 1) * dim));
        }
        (self as any).postMessage({ id, type: "progress", done: Math.min(i + BATCH, texts.length), total: texts.length });
      }
      (self as any).postMessage({ id, ok: true, vectors: out }, out.map((v) => v.buffer));
      return;
    }
  } catch (e: any) {
    (self as any).postMessage({ id, ok: false, error: e?.message ?? String(e) });
  }
};

export {};
