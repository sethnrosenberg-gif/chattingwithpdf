import { useState, useRef, useEffect, memo } from "react";
import { useShallow } from "zustand/react/shallow";
import { useApp } from "@/store/useApp";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Pin, Send, Sparkles, Quote, Download, Plus, Lightbulb } from "lucide-react";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { tokenize } from "@/lib/text";
import { cn } from "@/lib/utils";
import type { QueryHit } from "@/lib/types";

const HighlightedSnippet = memo(({ text, terms }: { text: string; terms: string[] }) => {
  // Highlight spans by stem-matching original tokens
  const re = /([A-Za-z][A-Za-z0-9'\-]+|\s+|[^A-Za-z\s]+)/g;
  const parts: { s: string; hit: boolean }[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const tok = m[0];
    if (/^[A-Za-z]/.test(tok)) {
      const t = tokenize(tok);
      const hit = t.some((x) => terms.includes(x));
      parts.push({ s: tok, hit });
    } else parts.push({ s: tok, hit: false });
  }
  return (
    <p className="font-serif text-[15px] leading-relaxed text-ink">
      {parts.map((p, i) =>
        p.hit ? <mark key={i} className="citation-mark text-ink">{p.s}</mark> : <span key={i}>{p.s}</span>
      )}
    </p>
  );
});

const EvidenceCard = memo(({ hit, idx, onJump }: { hit: QueryHit; idx: number; onJump: () => void }) => {
  return (
    <article className="group paper-card rounded-sm p-4 transition hover:shadow-paper">
      <header className="mb-2 flex items-baseline justify-between gap-2 text-[11px]">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-primary tabular-nums">[{idx + 1}]</span>
          <span className="font-mono text-ink-muted">p.{hit.chunk.page}</span>
          {hit.chunk.heading && (
            <span className="font-serif italic text-ink-soft truncate max-w-[200px]">· {hit.chunk.heading}</span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <div className="h-1 w-12 overflow-hidden rounded-full bg-paper-deep">
            <div className="h-full bg-primary" style={{ width: `${Math.round(hit.score * 100)}%` }} />
          </div>
          <span className="font-mono text-[10px] text-ink-muted tabular-nums">{Math.round(hit.score * 100)}</span>
        </div>
      </header>
      <HighlightedSnippet text={hit.chunk.text} terms={hit.matchedTerms} />
      <footer className="mt-3 flex items-center gap-3 text-[11px] text-ink-muted">
        <button onClick={onJump} className="inline-flex items-center gap-1 font-medium text-primary hover:underline">
          <Quote className="h-3 w-3" /> Show in document
        </button>
        <span className="font-mono">bm25 {hit.bm25.toFixed(2)} · sem {hit.semantic.toFixed(2)}</span>
      </footer>
    </article>
  );
});

const STARTERS = [
  "What is the main argument?",
  "List the key findings.",
  "Define the most important term.",
  "What evidence is given?",
];

export function Conversation() {
  const { activeDocId, activeThread, ask, retrievalMode, setMode, semanticReady, jumpToCitation, newThread, pinMessage, exportThread } = useApp();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [activeThread?.messages.length]);

  if (!activeDocId) return null;

  async function send(text?: string) {
    const query = (text ?? q).trim();
    if (!query) return;
    setBusy(true);
    setQ("");
    try { await ask(query); } finally { setBusy(false); }
  }

  function downloadThread() {
    const md = exportThread();
    const blob = new Blob([md], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `marginalia-thread-${Date.now()}.md`;
    a.click();
  }

  const messages = activeThread?.messages ?? [];

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between gap-2 border-b border-rule bg-paper px-4 py-2">
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
          <span className="smallcaps text-ink-soft">Inquiry</span>
        </div>
        <div className="flex items-center gap-2">
          <ToggleGroup
            type="single"
            value={retrievalMode}
            onValueChange={(v) => v && setMode(v as any)}
            size="sm"
          >
            <ToggleGroupItem value="lexical" className="h-7 px-2 text-[10px] font-mono uppercase">Lex</ToggleGroupItem>
            <ToggleGroupItem value="hybrid" className="h-7 px-2 text-[10px] font-mono uppercase" disabled={!semanticReady}>Hybrid</ToggleGroupItem>
            <ToggleGroupItem value="semantic" className="h-7 px-2 text-[10px] font-mono uppercase" disabled={!semanticReady}>Sem</ToggleGroupItem>
          </ToggleGroup>
          <Button variant="ghost" size="icon" onClick={newThread} title="New thread">
            <Plus className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" onClick={downloadThread} title="Export thread" disabled={!messages.length}>
            <Download className="h-4 w-4" />
          </Button>
        </div>
      </header>

      <ScrollArea className="flex-1" ref={scrollRef as any}>
        <div className="mx-auto max-w-2xl space-y-8 p-6">
          {messages.length === 0 && (
            <div className="space-y-6 py-8">
              <div>
                <div className="smallcaps text-primary">No generation. No guesses.</div>
                <h2 className="display mt-1 text-3xl text-ink">Ask the document.</h2>
                <p className="mt-3 max-w-md font-serif text-[15px] leading-relaxed text-ink-soft">
                  Marginalia retrieves the most relevant passages, ranks them, and shows you exactly where each one lives. Every answer is a quotation — never a fabrication.
                </p>
              </div>
              <div className="space-y-2">
                <div className="smallcaps text-ink-muted flex items-center gap-1.5">
                  <Lightbulb className="h-3 w-3" /> Try
                </div>
                <div className="flex flex-wrap gap-2">
                  {STARTERS.map((s) => (
                    <button key={s} onClick={() => send(s)} className="rounded-sm border border-rule bg-paper px-3 py-1.5 text-left font-serif text-sm italic text-ink-soft hover:border-primary hover:text-ink">
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={m.id} className={cn("animate-fade-up", m.role === "user" ? "" : "space-y-3")}>
              {m.role === "user" ? (
                <div className="flex items-baseline gap-3">
                  <span className="smallcaps text-primary shrink-0">Q.</span>
                  <p className="display text-xl text-ink">{m.text}</p>
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between">
                    <span className="smallcaps text-ink-muted">
                      {m.hits?.length ? `${m.hits.length} passages` : "No passages"}
                    </span>
                    <button
                      onClick={() => pinMessage(m.id)}
                      className={cn("rounded-sm p-1 hover:bg-paper-deep", m.pinned && "text-primary")}
                      title={m.pinned ? "Unpin" : "Pin"}
                    >
                      <Pin className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <div className="space-y-3">
                    {(m.hits ?? []).map((h, j) => (
                      <EvidenceCard
                        key={h.chunk.id + j}
                        hit={h}
                        idx={j}
                        onJump={() => jumpToCitation(h.chunk.page, h.chunk.text, h.chunk.id)}
                      />
                    ))}
                    {!m.hits?.length && (
                      <p className="font-serif italic text-ink-muted">{m.text}</p>
                    )}
                  </div>
                </>
              )}
            </div>
          ))}
          {busy && (
            <div className="flex items-center gap-2 text-sm text-ink-muted animate-ink-in">
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
              Searching…
            </div>
          )}
        </div>
      </ScrollArea>

      <div className="border-t border-rule bg-paper p-3">
        <div className="mx-auto flex max-w-2xl items-end gap-2">
          <Textarea
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
            }}
            placeholder="Ask anything about this document…"
            className="min-h-[44px] max-h-32 resize-none border-rule bg-card font-serif text-[15px] leading-snug"
            rows={1}
          />
          <Button onClick={() => send()} disabled={busy || !q.trim()} size="icon" className="h-11 w-11 shrink-0">
            <Send className="h-4 w-4" />
          </Button>
        </div>
        <div className="mx-auto mt-1.5 max-w-2xl text-center font-mono text-[10px] text-ink-muted">
          {semanticReady ? "Hybrid lexical + semantic · all on-device" : "Lexical mode · enable semantic in the right pane for nuance"}
        </div>
      </div>
    </div>
  );
}
