// A word-level diff for "Preview diff" on a Review finding (#43, part 19
// §19.3): the paragraph as it is against the rewrite the audit proposed.
// Display only - what is applied is the proposed text whole, through the
// write path; this never produces a patch anything writes.

export type DiffOp = { kind: "same" | "removed" | "added"; text: string };

function tokens(text: string): string[] {
  // Words and the whitespace between them, kept, so rejoining is lossless.
  return text.match(/\S+|\s+/g) ?? [];
}

/** Longest-common-subsequence word diff of `before` against `after`. */
export function wordDiff(before: string, after: string): DiffOp[] {
  const a = tokens(before);
  const b = tokens(after);
  // lengths[i][j]: LCS length of a[i..] and b[j..].
  const lengths: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0),
  );
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      lengths[i][j] =
        a[i] === b[j]
          ? lengths[i + 1][j + 1] + 1
          : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
    }
  }
  const ops: DiffOp[] = [];
  const push = (kind: DiffOp["kind"], text: string) => {
    const last = ops[ops.length - 1];
    if (last && last.kind === kind) last.text += text;
    else ops.push({ kind, text });
  };
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      push("same", a[i]);
      i += 1;
      j += 1;
    } else if (lengths[i + 1][j] >= lengths[i][j + 1]) {
      push("removed", a[i]);
      i += 1;
    } else {
      push("added", b[j]);
      j += 1;
    }
  }
  while (i < a.length) push("removed", a[i++]);
  while (j < b.length) push("added", b[j++]);
  return ops;
}
