# Lumen — Private In-Browser Document Chat

A fully client-side document chat application that processes PDF, DOCX, MD, HTML, and TXT files entirely in your browser. No data leaves your device.

## Features

- **Private & Secure**: All processing happens in-browser using IndexedDB
- **Multi-format Support**: PDF, DOCX, Markdown, HTML, and plain text
- **Smart Retrieval**: BM25 lexical search + heading-based semantic matching with RRF fusion
- **Safari Compatible**: Fixed lookbehind regex crash affecting Safari < 16.4
- **Unicode Support**: Tokenizes CJK, Cyrillic, Arabic, Greek, Hebrew text
- **Atomic Transactions**: No orphaned data from interrupted ingestion
- **Validated Settings**: Prevents zero-chunk bugs from tampered localStorage

## Quick Start

### Windows
Double-click `start.bat` — it will install dependencies and launch the dev server.

### Manual Start
```bash
npm install
npm run dev
```

The app opens at `http://localhost:5173`

## Build for Production

```bash
npm run build
```

The `dist/` folder contains a static site ready to deploy to:
- Netlify
- Vercel
- Cloudflare Pages
- AWS S3
- Any static host

## Usage

1. **Upload Documents**: Drag & drop or click to upload PDF, DOCX, MD, HTML, or TXT files
2. **Ask Questions**: Type queries in the chat panel
3. **View Citations**: Click citation chips to highlight source chunks in the reader
4. **Switch Modes**: Toggle between Lexical, Hybrid, and Semantic retrieval

## Architecture

### Core Fixes Applied

1. **Safari Crash Fix**: Replaced lookbehind regex `(?<=[.!?])\s+` with `matchAll`-based scanner
2. **Atomic Ingestion**: Single IndexedDB transaction for doc + chunks + blob
3. **Heading-as-Chunk**: Headings now emit searchable chunks instead of being skipped
4. **Unicode Tokenizer**: `\p{L}` regex with `u` flag supports all scripts
5. **Settings Validation**: Clamps `chunkSentences` to [1,6], `chunkOverlap` to [0, chunkSentences-1]
6. **UUID Doc IDs**: `crypto.randomUUID()` prevents collisions under bulk import

### File Structure

```
lumen/
├─ src/
│  ├─ lib/           # Core logic (db, ingest, chunker, score, tokenize, sentences, settings)
│  ├─ components/    # UI components (DropZone, Reader, ChatPanel, Sidebar, ModeToggle)
│  ├─ pages/         # Routes (Home, DocView, NotFound)
│  ├─ types.ts       # TypeScript definitions
│  ├─ App.tsx        # Router
│  ├─ main.tsx       # Entry point
│  └─ index.css      # Tailwind styles
├─ index.html
├─ package.json
├─ vite.config.ts
├─ tsconfig.json
└─ start.bat         # Windows launcher
```

## Retrieval Modes

- **Lexical**: BM25 with proximity bonus
- **Hybrid**: RRF fusion of BM25 + heading overlap (default)
- **Semantic**: Heading token overlap (true embeddings require `@xenova/transformers`)

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 15+ (iOS 15+)

## License

MIT
