import * as pdfjs from "pdfjs-dist";
// Vite worker import
// @ts-ignore
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import type { Chunk } from "./types";
import { tokenize } from "./text";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

export interface ParsedPage {
  page: number;
  text: string;
  width: number;
  height: number;
}

export async function parsePdf(file: File, onProgress?: (pct: number, label: string) => void): Promise<{ pages: ParsedPage[]; headings: { page: number; text: string }[]; bytes: ArrayBuffer }> {
  const bytes = await file.arrayBuffer();
  const doc = await pdfjs.getDocument({ data: bytes.slice(0) }).promise;
  const pages: ParsedPage[] = [];
  
  // To avoid memory explosion, we sample font sizes from a few pages instead of storing all runs
  const sampleSizes: number[] = [];
  const MAX_SAMPLE_PAGES = 30;
  
  // We'll collect headings in a single pass to avoid keeping all runs in memory
  const allHeadings: { page: number; text: string }[] = [];

  // 1. Pass to get font size distribution (sampling)
  const sampleStep = Math.max(1, Math.floor(doc.numPages / MAX_SAMPLE_PAGES));
  for (let p = 1; p <= doc.numPages; p += sampleStep) {
    const page = await doc.getPage(p);
    const tc = await page.getTextContent();
    for (const it of tc.items as any[]) {
      const tr = it.transform as number[];
      const fontSize = Math.hypot(tr[2], tr[3]) || Math.abs(tr[3]);
      if (fontSize > 1) sampleSizes.push(fontSize);
    }
  }
  sampleSizes.sort((a, b) => a - b);
  const medianSize = sampleSizes[Math.floor(sampleSizes.length / 2)] ?? 12;
  const headingThresh = medianSize * 1.3;

  for (let p = 1; p <= doc.numPages; p++) {
    const page = await doc.getPage(p);
    const viewport = page.getViewport({ scale: 1 });
    const tc = await page.getTextContent();
    
    let pageText = "";
    let curY: number | null = null;
    let curLine = { text: "", size: 0 };
    
    for (const it of tc.items as any[]) {
      const str: string = it.str ?? "";
      if (!str) continue;
      
      const tr = it.transform as number[];
      const fontSize = Math.hypot(tr[2], tr[3]) || Math.abs(tr[3]);
      const yPdf = tr[5];
      const h = it.height ?? fontSize;
      const ny = 1 - (yPdf + h) / viewport.height;

      // Heading detection (inline)
      if (curY === null || Math.abs(ny - curY) < 0.005) {
        curLine.text += str;
        curLine.size = Math.max(curLine.size, fontSize);
        curY = ny;
      } else {
        if (curLine.size >= headingThresh && curLine.text.trim().length > 2 && curLine.text.trim().length < 140) {
          allHeadings.push({ page: p, text: curLine.text.trim() });
        }
        curLine = { text: str, size: fontSize };
        curY = ny;
      }

      pageText += str;
      if (it.hasEOL) pageText += "\n"; else pageText += " ";
    }
    
    if (curLine.size >= headingThresh && curLine.text.trim()) {
      allHeadings.push({ page: p, text: curLine.text.trim() });
    }

    pages.push({ 
      page: p, 
      text: pageText.replace(/[ \t]+/g, " "),
      width: viewport.width, 
      height: viewport.height 
    });
    onProgress?.(p / doc.numPages, `Parsing page ${p}/${doc.numPages}`);
  }
  return { pages, headings: allHeadings, bytes };
}

// Adaptive sliding-window chunking with heading inheritance.
export function chunkPages(docId: string, pages: ParsedPage[], allHeadings: { page: number; text: string }[]): { chunks: Chunk[] } {
  const headingsByPage = new Map<number, string[]>();
  for (const h of allHeadings) {
    const arr = headingsByPage.get(h.page) ?? [];
    arr.push(h.text);
    headingsByPage.set(h.page, arr);
  }

  const TARGET = 480; // chars
  const OVERLAP = 80;
  const chunks: Chunk[] = [];
  let currentHeading: string | undefined;
  let idx = 0;

  for (const pg of pages) {
    const pageHeads = headingsByPage.get(pg.page) ?? [];
    if (pageHeads.length) currentHeading = pageHeads[0];
    const text = pg.text.replace(/\s+/g, " ").trim();
    if (!text) continue;
    let start = 0;
    while (start < text.length) {
      let end = Math.min(text.length, start + TARGET);
      const slice = text.slice(start, end);
      const lastStop = Math.max(slice.lastIndexOf(". "), slice.lastIndexOf("? "), slice.lastIndexOf("! "));
      if (lastStop > TARGET * 0.5) end = start + lastStop + 1;
      const piece = text.slice(start, end).trim();
      if (piece.length >= 40) {
        chunks.push({
          id: `${docId}:${idx}`,
          docId,
          idx,
          page: pg.page,
          heading: currentHeading,
          text: piece,
          tokens: tokenize(piece),
        });
        idx++;
      }
      if (end >= text.length) break;
      start = Math.max(end - OVERLAP, start + 1);
    }
  }
  return { chunks };
}
