import { useEffect, useRef, useState, lazy, Suspense } from "react";
import { useShallow } from "zustand/react/shallow";
import { useApp } from "@/store/useApp";
import { Library } from "@/components/marginalia/Library";
import { Conversation } from "@/components/marginalia/Conversation";
import { Outline } from "@/components/marginalia/Outline";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { FileText, UploadCloud } from "lucide-react";

const PdfReader = lazy(() => import("@/components/marginalia/PdfReader").then(m => ({ default: m.PdfReader })));

const Index = () => {
  const { docs, activeDocId, init, ingestFile, ingestStatus } = useApp(
    useShallow((s) => ({
      docs: s.docs,
      activeDocId: s.activeDocId,
      init: s.init,
      ingestFile: s.ingestFile,
      ingestStatus: s.ingestStatus,
    }))
  );
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => { init(); }, [init]);

  const active = docs.find((d) => d.id === activeDocId);

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const f = Array.from(e.dataTransfer.files).find((x) => x.type === "application/pdf");
    if (f) ingestFile(f, { embed: false });
  }

  return (
    <main
      className="flex h-screen w-screen overflow-hidden bg-background text-foreground"
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
    >
      <Library />

      {!active ? (
        <section className="relative flex-1 flex items-center justify-center p-8">
          <div className="max-w-xl text-center">
            <div className="smallcaps text-primary">Marginalia · v1</div>
            <h1 className="display mt-3 text-5xl md:text-6xl text-ink">
              Read closely.<br />
              <span className="italic text-primary">Question</span> precisely.
            </h1>
            <p className="mt-5 font-serif text-lg leading-relaxed text-ink-soft">
              A private reading room for your PDFs. No servers, no language models, no internet required to use. Just your documents and the words inside them.
            </p>
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) ingestFile(f, { embed: false });
              }}
            />
            <button
              onClick={() => fileRef.current?.click()}
              className="mt-8 inline-flex items-center gap-3 rounded-sm border border-primary bg-primary px-6 py-3 font-serif text-base text-primary-foreground shadow-paper transition hover:bg-primary-glow"
            >
              <UploadCloud className="h-5 w-5" /> Open a PDF
            </button>
            <p className="mt-3 font-mono text-[11px] text-ink-muted">…or drop one anywhere on this page.</p>
          </div>
        </section>
      ) : (
        <ResizablePanelGroup direction="horizontal" className="flex-1">
          <ResizablePanel defaultSize={45} minSize={28}>
            <Suspense fallback={<div className="flex h-full items-center justify-center bg-paper-deep text-ink-muted">Loading reader…</div>}>
              <PdfReader docId={active.id} pages={active.pages} />
            </Suspense>
          </ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel defaultSize={35} minSize={25}>
            <Conversation />
          </ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel defaultSize={20} minSize={15} className="bg-paper">
            <div className="flex items-center gap-2 border-b border-rule px-4 py-2">
              <FileText className="h-3.5 w-3.5 text-primary" />
              <div className="min-w-0 flex-1">
                <div className="truncate font-serif text-sm font-medium text-ink">{active.name}</div>
                <div className="font-mono text-[10px] text-ink-muted">{active.pages} pages</div>
              </div>
            </div>
            <div className="h-[calc(100%-48px)]">
              <Outline />
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      )}

      {dragOver && (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-paper/90 backdrop-blur-sm">
          <div className="rounded-sm border-2 border-dashed border-primary bg-paper px-12 py-10 text-center shadow-paper">
            <UploadCloud className="mx-auto h-8 w-8 text-primary" />
            <p className="display mt-3 text-2xl text-ink">Release to add to your library</p>
          </div>
        </div>
      )}

      {ingestStatus && (
        <div className="fixed bottom-4 right-4 z-40 w-80 rounded-sm border border-rule bg-card p-3 shadow-paper animate-fade-up">
          <div className="flex items-center justify-between text-[11px]">
            <span className="smallcaps text-primary">Working</span>
            <span className="font-mono text-ink-muted">{Math.round(ingestStatus.pct * 100)}%</span>
          </div>
          <p className="mt-1 truncate font-serif text-sm text-ink">{ingestStatus.label}</p>
          <div className="mt-2 h-0.5 overflow-hidden bg-paper-deep">
            <div className="h-full bg-primary transition-all" style={{ width: `${ingestStatus.pct * 100}%` }} />
          </div>
        </div>
      )}
    </main>
  );
};

export default Index;
