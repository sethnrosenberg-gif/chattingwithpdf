// Lightweight English text utilities. No external NLP, no internet.

const STOPWORDS = new Set(`a about above after again against all am an and any are aren as at be because been before being below between both but by can cannot could did do does doing don down during each few for from further had has have having he her here hers herself him himself his how i if in into is it its itself just me more most my myself no nor not now of off on once only or other our ours ourselves out over own same she should so some such than that the their theirs them themselves then there these they this those through to too under until up very was we were what when where which while who whom why will with would you your yours yourself yourselves`.split(/\s+/));

const TOKEN_RE = /[A-Za-z][A-Za-z0-9'-]{1,}/g;

// Tiny Porter-ish stemmer (handles common suffixes; not perfect, but fast & deterministic)
export function stem(w: string): string {
  let s = w;
  if (s.length < 4) return s;
  const suf = ["ingly","edly","ions","ing","ies","ied","ied","ers","est","ous","ive","ity","ment","ness","ally","ly","es","ed","er","s"];
  for (const x of suf) {
    if (s.endsWith(x) && s.length - x.length >= 3) { s = s.slice(0, -x.length); break; }
  }
  return s;
}

export function tokenize(text: string): string[] {
  const out: string[] = [];
  TOKEN_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = TOKEN_RE.exec(text)) !== null) {
    const w = m[0].toLowerCase().replace(/^['-]+|['-]+$/g, "");
    if (!w || w.length < 2) continue;
    if (STOPWORDS.has(w)) continue;
    out.push(stem(w));
  }
  return out;
}

// Keep raw tokens (with positions) for highlighting
export interface RawToken { word: string; start: number; end: number; }
export function tokenizeRaw(text: string): RawToken[] {
  const out: RawToken[] = [];
  TOKEN_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = TOKEN_RE.exec(text)) !== null) {
    out.push({ word: m[0], start: m.index, end: m.index + m[0].length });
  }
  return out;
}

export function sentenceSplit(text: string): string[] {
  // Robust enough for prose
  return text
    .replace(/\s+/g, " ")
    .match(/[^.!?]+[.!?]+(?=\s|$)|[^.!?]+$/g)
    ?.map((s) => s.trim())
    .filter(Boolean) ?? [text];
}

// Tiny synonym expander (manually curated, generic). Keeps queries client-side.
const SYN: Record<string, string[]> = {
  buy: ["purchase","acquire"],
  big: ["large","huge","massive"],
  small: ["tiny","little","minor"],
  fast: ["quick","rapid","speedy"],
  slow: ["sluggish","gradual"],
  start: ["begin","initiate","commence"],
  end: ["finish","conclude","terminate"],
  use: ["utilize","employ","apply"],
  show: ["display","present","demonstrate"],
  make: ["create","produce","build"],
  problem: ["issue","challenge","difficulty"],
  result: ["outcome","finding","conclusion"],
  method: ["approach","technique","procedure"],
  important: ["critical","essential","key","significant"],
  goal: ["objective","aim","target"],
  cost: ["price","expense"],
  help: ["assist","support","aid"],
};

export function expandQueryTerms(stems: string[]): string[] {
  const out = new Set(stems);
  for (const s of stems) {
    const syns = SYN[s];
    if (syns) for (const x of syns) out.add(stem(x));
  }
  return Array.from(out);
}

export function escapeRegex(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
