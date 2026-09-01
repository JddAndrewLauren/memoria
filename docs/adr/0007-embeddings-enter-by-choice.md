# Embeddings enter by choice, because a retrieval miss cannot be observed

Part 11 kept retrieval to FTS5 until a measured number said otherwise, and §45's
process — observe a real failure, turn it into a benchmark, then adopt — was to supply
that number. On 2026-09-01 the Thoreau corpus and its harness were retired and
`open-problems.md` §2.2 recorded that the gate had no instrument left. Re-grilling the
question the same day found that this gate can never fire for retrieval recall at all:
a paragraph that search did not return is invisible to the author, which is exactly
what part 11 §33.1 says of every index — *an index reports nothing about its own
recall*. Waiting for an observed failure here is waiting for something structurally
unobservable, and the poc-plan already drew the conclusion: "FTS5-first without
measurement is just under-building." The real archive is journal entries and email,
where prose about an event rarely repeats the words of the evidence behind it. **We
decided that semantic embeddings enter by choice**, with the shape fixed now and the
build scheduled at M2 against fixture records, exactly as the FTS5 index (#7) was
built before any archive existed.

## The shape

- **One store.** A `sqlite-vec` virtual table beside the FTS5 table in
  `.memoria/index.db` — same file, same connect-per-call rule (ADR-0004), deleted by the
  same unlink at `memoria rebuild`. `sqlite-vec` is pre-1.0 and is pinned. No vector
  database: Qdrant and LanceDB buy nothing at this scale and cost a process.
- **A local CPU model at rebuild.** Production has no GPU, so the embedder is an ONNX
  model through `fastembed` (bge-small-en-v1.5 to start; `model2vec`'s static
  `potion-retrieval` is the lighter fallback). It costs no subscription capacity and no
  metered spend, which is what part 08 §12.1's "nothing that needs a model runs unasked"
  protects; it is a model nonetheless, and this ADR records that it runs at rebuild.
- **Nothing leaves the machine.** A metered embedding API (Voyage, effectively free at
  this scale) was rejected because the whole archive would be sent to a third party
  (part 17 §48).
- **`search_semantic(query, filters)`** ships on the §25 surface with its own clause in
  the §33 scope line, so a session can say what was embedded and searched. Cluster
  summaries are never embedded: that would be a search over compressions, not evidence.
- **The instrument is a labelled query set the author grows in use**, started the day
  the archive arrives. It is the successor harness's first number (part 15 §43.14) and
  the only way a retrieval miss becomes visible.

## Consequences

- §45 is reversed by choice a second time in one day, after ADR-0005. The failure-first
  process still governs everything else on its list. `open-problems.md` §5 carries the
  cost: if the labelled set later shows FTS5 alone would have done, this was
  over-building.
- Part 16's M2 forces the `search_semantic` signature; `open-problems.md` §2.2 closes;
  the poc-plan's "pending the benchmark number" row closes.
- The ONNX runtime and its model weights are the core's first non-trivial runtime
  dependency; the desktop and hosted builds must carry them.
