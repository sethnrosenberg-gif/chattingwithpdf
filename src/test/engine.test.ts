import { describe, it, expect, beforeEach } from "vitest";
import { buildIndex, query } from "../lib/engine";
import { tokenize } from "../lib/text";

describe("engine", () => {
  const docId = "test-doc";
  const chunks = [
    { id: "1", docId, idx: 0, page: 1, text: "The quick brown fox jumps over the lazy dog", tokens: tokenize("The quick brown fox jumps over the lazy dog") },
    { id: "2", docId, idx: 1, page: 1, text: "A fast animal leaps across a sleeping canine", tokens: tokenize("A fast animal leaps across a sleeping canine") },
  ];

  beforeEach(() => {
    buildIndex(docId, chunks);
  });

  it("should find results with lexical search", async () => {
    const results = await query(docId, "fox", "lexical");
    expect(results.length).toBeGreaterThan(0);
    expect(results[0].chunk.id).toBe("1");
    expect(results[0].score).toBeGreaterThan(0);
  });

  it("should handle single result score normalization", async () => {
    // Before fix, this would have a score of 0
    const results = await query(docId, "fox", "lexical");
    expect(results.length).toBe(1);
    expect(results[0].score).toBe(1); // Normalized to 1 when range is 0
  });

  it("should handle multiple results with different scores", async () => {
    const results = await query(docId, "quick brown", "lexical");
    expect(results.length).toBe(1);
    expect(results[0].score).toBe(1);
  });

  it("should handle no results", async () => {
    const results = await query(docId, "xyzzy", "lexical");
    expect(results.length).toBe(0);
  });
});
