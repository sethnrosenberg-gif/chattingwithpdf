// Pure-JS BM25 implementation with optional field boosts.
import { tokenize } from "./text";

export interface BM25Doc { id: string; tokens: string[] }

export class BM25 {
  private k1 = 1.4;
  private b = 0.75;
  private docs = new Map<string, { tokens: string[]; len: number; tf: Map<string, number> }>();
  private df = new Map<string, number>();
  private inv = new Map<string, Set<string>>();
  private avgdl = 0;
  private N = 0;

  add(id: string, tokens: string[]) {
    const tf = new Map<string, number>();
    for (const t of tokens) tf.set(t, (tf.get(t) ?? 0) + 1);
    this.docs.set(id, { tokens, len: tokens.length, tf });
    const seen = new Set(tokens);
    for (const t of seen) {
      this.df.set(t, (this.df.get(t) ?? 0) + 1);
      let s = this.inv.get(t);
      if (!s) {
        s = new Set();
        this.inv.set(t, s);
      }
      s.add(id);
    }
  }

  finalize() {
    this.N = this.docs.size;
    let tot = 0;
    for (const d of this.docs.values()) tot += d.len;
    this.avgdl = tot / Math.max(1, this.N);
  }

  idf(term: string): number {
    const df = this.df.get(term) ?? 0;
    return Math.log(1 + (this.N - df + 0.5) / (df + 0.5));
  }

  score(id: string, terms: string[]): { score: number; matched: Set<string> } {
    const d = this.docs.get(id);
    if (!d) return { score: 0, matched: new Set() };
    let s = 0;
    const matched = new Set<string>();
    for (const t of terms) {
      const tf = d.tf.get(t);
      if (!tf) continue;
      matched.add(t);
      const idf = this.idf(t);
      const denom = tf + this.k1 * (1 - this.b + this.b * (d.len / (this.avgdl || 1)));
      s += idf * (tf * (this.k1 + 1)) / denom;
    }
    return { score: s, matched };
  }

  search(query: string, terms: string[], topK = 50): { id: string; score: number; matched: Set<string> }[] {
    if (!terms.length) terms = tokenize(query);
    const out: { id: string; score: number; matched: Set<string> }[] = [];
    
    const candidates = new Set<string>();
    for (const t of terms) {
      const docs = this.inv.get(t);
      if (docs) {
        for (const d of docs) candidates.add(d);
      }
    }

    for (const id of candidates) {
      const r = this.score(id, terms);
      if (r.score > 0) out.push({ id, score: r.score, matched: r.matched });
    }
    out.sort((a, b) => b.score - a.score);
    return out.slice(0, topK);
  }
}
