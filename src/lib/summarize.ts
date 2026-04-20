// TextRank summary + RAKE keyphrases + simple entity extraction. All deterministic, offline.
import { sentenceSplit, tokenize, stem } from "./text";

function cosineSets(a: Set<string>, b: Set<string>): number {
  if (!a.size || !b.size) return 0;
  let inter = 0;
  for (const x of a) if (b.has(x)) inter++;
  return inter / Math.sqrt(a.size * b.size);
}

export function textRankSummary(text: string, topN = 5): string[] {
  const originalSents = sentenceSplit(text).filter((s) => s.length > 30 && s.length < 400);
  if (originalSents.length <= topN) return originalSents;
  
  // Cap the number of sentences to avoid quadratic memory explosion (N*N matrix)
  // 400 sentences is plenty for a good summary and keeps the matrix under ~1.3MB
  const sents = originalSents.length > 400 
    ? [...originalSents.slice(0, 200), ...originalSents.slice(-200)] 
    : originalSents;

  const sets = sents.map((s) => new Set(tokenize(s)));
  const N = sents.length;
  // Build similarity matrix
  const sim: number[][] = Array.from({ length: N }, () => new Array(N).fill(0));
  for (let i = 0; i < N; i++) {
    for (let j = i + 1; j < N; j++) {
      const v = cosineSets(sets[i], sets[j]);
      sim[i][j] = v; sim[j][i] = v;
    }
  }
  // Power iteration
  let scores = new Array(N).fill(1 / N);
  const damp = 0.85;
  for (let iter = 0; iter < 30; iter++) {
    const next = new Array(N).fill((1 - damp) / N);
    for (let i = 0; i < N; i++) {
      let row = 0;
      for (let j = 0; j < N; j++) row += sim[i][j];
      if (!row) continue;
      for (let j = 0; j < N; j++) {
        if (sim[i][j]) next[j] += damp * (sim[i][j] / row) * scores[i];
      }
    }
    scores = next;
  }
  const ranked = sents.map((s, i) => ({ s, i, score: scores[i] }))
    .sort((a, b) => b.score - a.score)
    .slice(0, topN)
    .sort((a, b) => a.i - b.i)
    .map((x) => x.s);
  return ranked;
}

const STOP = new Set(`a about above after again against all am an and any are aren as at be because been before being below between both but by can cannot could did do does doing don down during each few for from further had has have having he her here hers herself him himself his how i if in into is it its itself just me more most my myself no nor not now of off on once only or other our ours ourselves out over own same she should so some such than that the their theirs them themselves then there these they this those through to too under until up very was we were what when where which while who whom why will with would you your yours yourself yourselves`.split(/\s+/));

export function rakeKeyphrases(text: string, topN = 10): string[] {
  const cleaned = text.replace(/\s+/g, " ");
  const phrases = cleaned.split(/[.,;:!?\-\(\)\[\]\"\n\r]+|(?:\s(?:and|or|but|of|for|to|in|on|with|by|the|a|an)\s)/gi)
    .map((p) => p.trim().toLowerCase())
    .filter((p) => p && p.length > 3 && p.length < 60 && !/^\d+$/.test(p));

  const freq = new Map<string, number>();
  const deg = new Map<string, number>();
  for (const ph of phrases) {
    const ws = ph.split(/\s+/).filter((w) => w.length > 2 && !STOP.has(w));
    if (!ws.length) continue;
    const dl = ws.length - 1;
    for (const w of ws) {
      freq.set(w, (freq.get(w) ?? 0) + 1);
      deg.set(w, (deg.get(w) ?? 0) + dl);
    }
  }
  const wScore = new Map<string, number>();
  for (const [w, f] of freq) wScore.set(w, ((deg.get(w) ?? 0) + f) / f);
  const phraseScore = new Map<string, number>();
  for (const ph of phrases) {
    const ws = ph.split(/\s+/).filter((w) => w.length > 2 && !STOP.has(w));
    if (ws.length < 1 || ws.length > 4) continue;
    const s = ws.reduce((a, w) => a + (wScore.get(w) ?? 0), 0);
    phraseScore.set(ph, Math.max(phraseScore.get(ph) ?? 0, s));
  }
  return Array.from(phraseScore.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, topN * 2)
    .map(([p]) => p)
    .filter((p, i, arr) => arr.findIndex((q) => q.includes(p) || p.includes(q)) === i)
    .slice(0, topN);
}

// Simple proper-noun entity extraction (capitalized sequences not at sentence start).
export function extractEntities(text: string, topN = 12): string[] {
  const counts = new Map<string, number>();
  const sents = sentenceSplit(text);
  for (const s of sents) {
    const re = /\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})\b/g;
    let m: RegExpExecArray | null;
    let first = true;
    while ((m = re.exec(s)) !== null) {
      const phrase = m[1];
      if (first && m.index <= 1) { first = false; continue; }
      first = false;
      if (phrase.length < 3) continue;
      if (STOP.has(phrase.toLowerCase())) continue;
      counts.set(phrase, (counts.get(phrase) ?? 0) + 1);
    }
  }
  return Array.from(counts.entries())
    .filter(([, c]) => c >= 2)
    .sort((a, b) => b[1] - a[1])
    .slice(0, topN)
    .map(([p]) => p);
}
