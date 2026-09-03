# Memoria

## Agent skills

### Issue tracker

GitHub Issues on `JddAndrewLauren/memoria`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles, each label string equal to its name, plus the non-triage
`plan` role. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Visual verification

**No routine visual gate** (decision 2026-09-02, clarified 2026-09-03). There is no
`docs/SURFACES.md` surface registry, and no wrap-up, review or PR is expected to
screenshot the app or walk it in a browser. The vitest suite in `ui/` covers UI
behaviour and is the standing UI gate. Do not add a visual step to a routine
workflow, and do not re-raise the missing registry as a gap.

**Browser tooling is not forbidden.** The rule above is about what runs *every time*,
not about what the repo may use. Driving the app in a real browser is the right tool
for a task that genuinely needs layout, scroll position or paint — a milestone gate
walk (`docs/gates/`), or diagnosing a rendering bug behaviour tests cannot see — and
an agent should reach for it there rather than handing the work back. jsdom cannot
substitute: it has no `scrollIntoView` and every layout measurement reads 0, so
"landed on the paragraph" and "kept my place" are unobservable in the vitest suite by
construction.

So: **routine work, no browser; a gate or a layout bug, use one.** Prefer a scripted,
headless run whose output is an artifact someone can check over a screenshot nobody
reads.
