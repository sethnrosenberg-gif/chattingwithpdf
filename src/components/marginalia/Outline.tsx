import { useApp } from "@/store/useApp";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";

export function Outline() {
  const { headings, summary, keyphrases, entities, jumpToCitation, semanticReady, enableSemantic, ingestStatus } = useApp(
    useShallow((s) => ({
      headings: s.headings,
      summary: s.summary,
      keyphrases: s.keyphrases,
      entities: s.entities,
      jumpToCitation: s.jumpToCitation,
      semanticReady: s.semanticReady,
      enableSemantic: s.enableSemantic,
      ingestStatus: s.ingestStatus,
    }))
  );

  return (
    <ScrollArea className="h-full">
      <div className="space-y-8 p-6">
        <section>
          <div className="smallcaps text-primary">Précis</div>
          <h3 className="display mt-1 text-xl text-ink">Extractive summary</h3>
          <ol className="mt-3 space-y-2 font-serif text-[15px] leading-relaxed text-ink-soft">
            {summary.length === 0 && <li className="text-ink-muted">No summary yet.</li>}
            {summary.map((s, i) => (
              <li key={i} className="border-l-2 border-primary/40 pl-3">{s}</li>
            ))}
          </ol>
        </section>

        {keyphrases.length > 0 && (
          <section>
            <div className="smallcaps text-ink-muted">Key phrases</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {keyphrases.map((k) => (
                <span key={k} className="rounded-sm bg-paper-deep px-2 py-1 font-mono text-[11px] text-ink-soft">
                  {k}
                </span>
              ))}
            </div>
          </section>
        )}

        {entities.length > 0 && (
          <section>
            <div className="smallcaps text-ink-muted">Named entities</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {entities.map((e) => (
                <span key={e} className="rounded-sm border border-primary/30 px-2 py-1 font-serif text-xs text-primary">
                  {e}
                </span>
              ))}
            </div>
          </section>
        )}

        <section>
          <div className="smallcaps text-ink-muted">Outline</div>
          {headings.length === 0 ? (
            <p className="mt-2 text-xs text-ink-muted">No headings detected in this document.</p>
          ) : (
            <ul className="mt-2 space-y-1">
              {headings.slice(0, 60).map((h, i) => (
                <li key={i}>
                  <button
                    className="group flex w-full items-baseline gap-2 rounded-sm px-2 py-1 text-left hover:bg-paper-deep"
                    onClick={() => jumpToCitation(h.page, h.text, "heading")}
                  >
                    <span className="font-mono text-[10px] text-ink-muted tabular-nums">p.{String(h.page).padStart(3, "·")}</span>
                    <span className="font-serif text-sm text-ink-soft group-hover:text-ink">{h.text}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {!semanticReady && (
          <section className="paper-card rounded-sm p-4">
            <div className="smallcaps text-primary">Optional</div>
            <h4 className="display mt-1 text-base text-ink">Enable semantic search</h4>
            <p className="mt-2 text-xs text-ink-muted">
              Adds an on-device neural model (~25 MB, one-time download). After it loads, all queries run locally — no further internet needed.
            </p>
            <Button
              size="sm"
              className="mt-3"
              variant="default"
              disabled={!!ingestStatus}
              onClick={() => enableSemantic()}
            >
              {ingestStatus ? ingestStatus.label : "Enable semantic mode"}
            </Button>
          </section>
        )}
      </div>
    </ScrollArea>
  );
}
