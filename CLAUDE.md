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

This repo has **no visual gate**, by decision on 2026-09-02 — no `docs/SURFACES.md`,
no screenshot capture, no Playwright. The vitest suite in `ui/` covers UI behaviour
and is the only UI gate. Skip visual verification rather than improvising one; do not
re-raise the missing registry as a gap. Revisit if the reading surfaces start
regressing in ways behaviour tests cannot see.
