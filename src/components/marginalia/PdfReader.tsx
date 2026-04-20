import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
// @ts-ignore
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import "react-pdf/dist/Page/TextLayer.css";
import { store } from "@/lib/store";
import { useApp } from "@/store/useApp";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

interface Props { docId: string; pages: number }

export function PdfReader({ docId, pages }: Props) {
  const [data, setData] = useState<Uint8Array | null>(null);
  const [page, setPage] = useState(1);
  const [scale, setScale] = useState(1.1);
  const [pageWidth, setPageWidth] = useState<number>(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const citation = useApp((s) => s.citation);

  useEffect(() => {
    let alive = true;
    (async () => {
      const buf = await store.getBlob(docId);
      if (alive && buf) setData(new Uint8Array(buf));
    })();
    return () => { alive = false; };
  }, [docId]);

  const [renderCounter, setRenderCounter] = useState(0);
  const lastCitationRef = useRef<string | null>(null);

  useEffect(() => {
    if (!citation) return;
    
    if (citation.page === page) {
      // already on page, try to highlight immediately
      highlightInPage(citation.text);
    } else {
      // jump to page, highlight will trigger via onRenderSuccess
      lastCitationRef.current = citation.text;
      setPage(citation.page);
    }
  }, [citation, page]); // included page to handle manual jumps

  useEffect(() => {
    const onResize = () => {
      if (!containerRef.current) return;
      const w = containerRef.current.clientWidth - 24;
      setPageWidth(Math.max(320, Math.min(900, w)));
    };
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  function highlightInPage(text: string) {
    const root = containerRef.current;
    if (!root) return;
    // remove old highlights
    root.querySelectorAll(".pdf-highlight").forEach((n) => n.remove());
    const layer = root.querySelector(".react-pdf__Page__textContent") as HTMLElement | null;
    if (!layer) return;
    const layerRect = layer.getBoundingClientRect();
    const spans = Array.from(layer.querySelectorAll("span")) as HTMLSpanElement[];
    // Build searchable string with index map
    const norm = (s: string) => s.toLowerCase().replace(/\s+/g, " ");
    const target = norm(text).slice(0, 80); // first ~80 chars are enough to locate
    const words = target.split(" ").filter((w) => w.length > 2).slice(0, 8);
    if (!words.length) return;

    // Find consecutive spans whose combined text contains most words
    let bestStart = -1, bestEnd = -1, bestHits = 0;
    const windowSize = 30; // slightly larger window for safety
    for (let i = 0; i < spans.length; i++) {
      let combined = "";
      for (let j = i; j < Math.min(spans.length, i + windowSize); j++) {
        combined += " " + (spans[j].textContent || "");
        const c = norm(combined);
        let hits = 0;
        for (const w of words) if (c.includes(w)) hits++;
        
        // If we found a significantly better match, or all words
        if (hits > bestHits) { 
          bestHits = hits; bestStart = i; bestEnd = j; 
        }
        if (hits === words.length && hits > 1) break;
      }
      if (bestHits === words.length && bestHits > 1) break;
    }
    
    // Require at least 50% of words or 100% of short queries to avoid false positives
    const miniThresh = Math.max(1, Math.floor(words.length * 0.5));
    if (bestStart < 0 || bestHits < miniThresh) return;
    let scrolled = false;
    for (let i = bestStart; i <= bestEnd; i++) {
      const r = spans[i].getBoundingClientRect();
      const div = document.createElement("div");
      div.className = "pdf-highlight";
      div.style.left = (r.left - layerRect.left) + "px";
      div.style.top = (r.top - layerRect.top) + "px";
      div.style.width = r.width + "px";
      div.style.height = r.height + "px";
      layer.appendChild(div);
      if (!scrolled) {
        spans[i].scrollIntoView({ block: "center", behavior: "smooth" });
        scrolled = true;
      }
    }
  }

  return (
    <div className="flex h-full flex-col bg-paper-deep">
      <div className="flex items-center justify-between gap-2 border-b border-rule bg-paper px-4 py-2">
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <div className="font-mono text-xs text-ink-soft tabular-nums">
            <input
              type="number"
              value={page}
              min={1}
              max={pages}
              onChange={(e) => setPage(Math.min(pages, Math.max(1, +e.target.value || 1)))}
              className="w-12 bg-transparent text-center outline-none"
            />
            <span className="text-ink-muted">/ {pages}</span>
          </div>
          <Button variant="ghost" size="icon" onClick={() => setPage((p) => Math.min(pages, p + 1))} disabled={page >= pages}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" onClick={() => setScale((s) => Math.max(0.6, s - 0.15))}>
            <ZoomOut className="h-4 w-4" />
          </Button>
          <span className="font-mono text-xs text-ink-muted w-10 text-center">{Math.round(scale * 100)}%</span>
          <Button variant="ghost" size="icon" onClick={() => setScale((s) => Math.min(2.4, s + 0.15))}>
            <ZoomIn className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <div ref={containerRef} className="flex-1 overflow-auto px-3 py-6">
        {data ? (
          <div className="mx-auto w-fit">
            <Document file={{ data }} loading={<div className="p-12 text-ink-muted">Loading…</div>}>
              <div className="bg-white shadow-paper">
                <Page
                  pageNumber={page}
                  width={pageWidth || undefined}
                  scale={scale}
                  renderAnnotationLayer={false}
                  renderTextLayer={true}
                  onRenderSuccess={() => {
                    setRenderCounter(c => c + 1);
                    if (lastCitationRef.current) {
                      highlightInPage(lastCitationRef.current);
                      lastCitationRef.current = null;
                    } else if (citation && citation.page === page) {
                      highlightInPage(citation.text);
                    }
                  }}
                />
              </div>
            </Document>
          </div>
        ) : (
          <div className="p-12 text-ink-muted">Opening document…</div>
        )}
      </div>
    </div>
  );
}
