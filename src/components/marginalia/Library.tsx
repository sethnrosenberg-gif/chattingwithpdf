import { useShallow } from "zustand/react/shallow";
import { useApp } from "@/store/useApp";
import { Button } from "@/components/ui/button";
import { Trash2, FileText, Plus } from "lucide-react";
import { useRef } from "react";
import { cn } from "@/lib/utils";

export function Library() {
  const { docs, activeDocId, setActive, removeDoc, ingestFile } = useApp();
  const fileRef = useRef<HTMLInputElement>(null);

  return (
    <aside className="flex h-full w-72 flex-col border-r border-rule bg-sidebar">
      <div className="border-b border-rule p-4">
        <div className="smallcaps text-ink-muted">Marginalia</div>
        <h1 className="display mt-1 text-2xl text-ink">Your library</h1>
        <p className="mt-1 text-xs text-ink-muted">Everything stays on this device.</p>
      </div>
      <div className="p-3">
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={async (e) => {
            const f = e.target.files?.[0];
            if (f) await ingestFile(f, { embed: false });
            e.target.value = "";
          }}
        />
        <Button onClick={() => fileRef.current?.click()} className="w-full" variant="default">
          <Plus className="mr-2 h-4 w-4" /> Add a PDF
        </Button>
      </div>
      <div className="flex-1 overflow-auto px-2 pb-3">
        {docs.length === 0 && (
          <p className="px-3 py-6 text-sm text-ink-muted">No documents yet. Drop a PDF to begin.</p>
        )}
        {docs.map((d) => (
          <button
            key={d.id}
            onClick={() => setActive(d.id)}
            className={cn(
              "group mb-1 flex w-full items-start gap-2 rounded-sm px-3 py-2 text-left transition",
              d.id === activeDocId
                ? "bg-paper-deep text-ink"
                : "text-ink-soft hover:bg-sidebar-accent"
            )}
          >
            <FileText className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
            <div className="min-w-0 flex-1">
              <div className="truncate font-serif text-[15px] font-medium leading-tight">{d.name}</div>
              <div className="mt-0.5 font-mono text-[10px] text-ink-muted">
                {d.pages}p · {(d.size / 1024 / 1024).toFixed(1)}MB {d.hasEmbeddings && "· semantic"}
              </div>
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); if (confirm(`Remove "${d.name}"?`)) removeDoc(d.id); }}
              className="opacity-0 transition group-hover:opacity-100"
              aria-label="Delete"
            >
              <Trash2 className="h-3.5 w-3.5 text-ink-muted hover:text-destructive" />
            </button>
          </button>
        ))}
      </div>
      <div className="border-t border-rule p-3 text-[10px] text-ink-muted">
        <p>No servers. No AI. No tracking.<br />Open-source local search.</p>
      </div>
    </aside>
  );
}
