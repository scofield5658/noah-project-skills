# Fixed Knowledge-Base Schema

Read this reference before selecting a destination, discovering existing notes, compiling sources, archiving a plan, or reporting health findings.

## Topology

```text
knowledge_root/
├── Clippings/                 optional temporary Web Clipper inbox
├── raw/
│   └── <domain-id>/           source evidence
├── wiki/
│   ├── <domain-id>/           compiled system knowledge
│   ├── concepts/              stable cross-domain concepts
│   └── archives/              reusable conclusions from complex Q&A
├── plan/                      user-finalized execution plans
└── health-checks/             dated issue reports
```

This lifecycle is fixed. Domain IDs are configurable; stage names are not.

## Document Contract

The knowledge base declares its format at `.knowledge-agent/knowledge-base.yaml`:

```yaml
schema_version: 1
document_contract: knowledge-markdown/v1
```

This file contains no personal path, remote Wiki target, credential, or publishing preference. It is valid with or without Git. An unknown schema or contract blocks automatic creation and material rewriting until a supported contract is selected.

The `knowledge-markdown/v1` portable subset is:

- UTF-8 Markdown with YAML frontmatter. `title` is the title source of truth; the first body H1 may be omitted, but when present it must match `title`.
- Headings, paragraphs, ordered/unordered/task lists, block quotes, GFM tables, fenced code, inline code, and footnotes are supported.
- Use canonical `<br>` for table-cell line breaks. Do not nest block structures inside a table cell, and escape a literal `|` in inline code.
- Fenced code should declare a language. Preserve unknown languages as source text rather than guessing a conversion.
- Links may be HTTP(S), knowledge-root-relative paths, or supported wikilinks. External repository paths follow the repository declaration rule below.
- Obsidian wikilinks, embeds, callouts, highlights, and comments are controlled extensions; Obsidian itself is not required.
- Mermaid uses a fenced block with language `mermaid`. Draw.io uses an explicit knowledge-root-relative `.drawio` reference.
- Raw HTML is limited to canonical `<br>` and machine-managed HTML comments. Any other HTML needs a defined lossless parsing rule before entering the contract.

A new syntax enters the supported format only when the contract, local generation/lint behavior and content-preservation tests agree; when an online adapter is actually used, its conversion/readback must also preserve the new syntax. Do not create permanent one-document exceptions.

The active authoring Profile can personalize template, tone, sections, and diagram preference. It cannot relax this contract or the path and content-safety rules.

## Destination Rules

| Content | Destination | Boundary |
| --- | --- | --- |
| New source or clipped material | `raw/<domain-id>/` | Preserve source identity and evidence gaps |
| Compiled system knowledge | `wiki/<domain-id>/` | A configured domain owns the subject |
| Stable cross-domain concept | `wiki/concepts/` | Concept is reusable across multiple domains |
| Stable Q&A conclusion/checklist/comparison | `wiki/archives/` | Do not archive transient conversation |
| Approved execution plan | `plan/` | User has finalized the plan |
| Health report | `health-checks/` | Default is report-only, not repair |

Cross-domain source material still needs a primary raw domain when one system owns the evidence. If ownership is genuinely shared and no destination is clear, ask; do not duplicate the full note across domains.

## Discovery Order

1. Select the stage required by the request.
2. Select the configured domain or stage-specific directory.
3. Inspect frontmatter: `kb_stage`, `bucket`, `status`, `source_refs`, `related_notes`, `last_reviewed`.
4. Follow relevant wikilinks, embeds, concepts, and archives only as needed.
5. Prefer updating a nearby existing page over creating a near-duplicate.

Use stage, domain, frontmatter and relevant links for discovery; a global `INDEX.md` is not required.

## Naming

- Raw: `YYYYMMDD-<topic>-source.md`
- Wiki: `YYYYMMDD-<service>-<module>-<category>.md`
- Archive: `YYYYMMDD-<topic>-archive.md`
- Plan: `YYYYMMDD-<topic>-execution-plan.md`
- Health check: `YYYYMMDD-<scope>-health-check.md`

Use date-first ASCII slugs unless the user requests another filename style. Update an existing stable filename when the topic is the same.

## Frontmatter

Minimum maintained fields:

```yaml
---
kb_stage: raw|wiki|plan|health-check
bucket: <domain-id>|concepts|archives|vault
source_refs: []
related_notes: []
last_reviewed: YYYY-MM-DD
status: captured|seeded|active|draft|archived|approved|baseline|needs-raw|needs-repair
path_base: knowledge_root       # include when the note contains local filesystem references
---
```

`bucket` stores the resolved `domain.id`. Stage-specific notes may use `concepts`, `archives`, or `vault`.

Evidence expectations:

- Raw notes identify the source, origin, capture status, and missing material.
- Wiki notes cite at least one source unless explicitly marked `needs-raw`.
- Concept pages backlink to the domain pages they consolidate.
- Archive pages state why the result is reusable and cite source pages.
- Plan pages state that the plan is user-finalized and preserve prerequisites, validation, and risk.
- Health reports cite every page they flag.
- Local filesystem references use `/`-separated paths relative to `knowledge_root`; never persist a personal home-directory absolute path or `file://` URI.
- External repository evidence declares `'repository:<repository-name>=<safe-remote-url>'` in `source_refs`, then cites code as `<repository-name>/<repository-relative-path>`. Do not persist workstation layout prefixes such as `Codes/Work/...`.

## Health Checks

Check, when relevant:

- missing or invalid frontmatter
- wiki pages without raw/source evidence
- broken wikilinks and weak `related_notes`
- orphan candidates and duplicate filenames/topics
- stale `last_reviewed` values
- repeated themes that deserve a concept page
- stable conclusions that should have been archived
- any real discovery problem caused by absence of a global index
- personal absolute paths (`local_absolute_path`) that would leak machine-specific information during sharing
- workstation-layout paths (`local_workspace_path`) that expose irrelevant local directory organization

`lint` assigns each finding one of three severities:

- `blocking`: possible path disclosure, invalid/missing frontmatter, title/H1 conflict, unknown HTML, malformed table, or another structure that may lose content.
- `warning`: broken/missing resource, Mermaid not yet rendered online, noncanonical `<br/>`, workstation path, or another issue that remains representable but needs review.
- `suggestion`: optional writing or reading-experience improvement.

Fix blocking findings before treating new or materially rewritten notes as ready. This Skill does not perform online synchronization; a downstream publisher must independently validate its input. Report warnings to the user; suggestions never block saving or synchronization by themselves.

Write findings, impact, and suggested repair. Do not modify core notes unless the user explicitly requests a repair pass.

Lint is auxiliary: it does not validate every status value, review date, semantic claim or reference. Contract/Profile status and source quality require separate review.
