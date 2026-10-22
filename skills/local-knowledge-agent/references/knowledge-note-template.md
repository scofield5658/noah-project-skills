# Knowledge Note Templates

Read the relevant template before creating or materially rewriting a note. Replace angle-bracket fields with factual values and remove unused guidance.

## Raw Source

```markdown
---
title: <topic>
kb_stage: raw
bucket: <domain-id>
source_refs:
  - <url-or-local-source>
related_notes: []
last_reviewed: <YYYY-MM-DD>
status: captured
path_base: knowledge_root
---

# <Topic>

## Source Identity

- Source type:
- Origin:
- Capture status:

## Why It Matters

- Relevance to the configured domain:

## Capture Coverage

- Captured:
- Missing:
- Attachments or local assets:

## Candidate Compile Targets

- Wiki page:
- Concept page:
```

## Compiled Wiki Page

```markdown
---
title: <service-module-topic>
kb_stage: wiki
bucket: <domain-id>
source_refs:
  - raw/<domain-id>/<source-note>.md
  # For each external repository used below, add once:
  # - 'repository:<repository-name>=<safe-fetch-remote-url>'
related_notes:
  - wiki/<domain-id>/<related-note>.md
last_reviewed: <YYYY-MM-DD>
status: active
path_base: knowledge_root
---

# <Title>

## Summary

<Stable conclusion in one short paragraph.>

## Scope

- In scope:
- Out of scope:

## Main Body

Use the structure the topic requires: stages, rules, comparison, design decision, incident findings, or implementation panorama.

For a complex maintainable diagram, save `assets/<note-stem>-<diagram-name>.drawio` beside this Wiki area and embed it as `![[assets/<note-stem>-<diagram-name>.drawio]]`. Keep simple or existing Mermaid fenced blocks as Mermaid.

## Sources and Evidence Gaps

- Confirmed sources:
- Repository code references use `<repository-name>/<repository-relative-path>` only after the matching `source_refs` declaration.
- Missing evidence:

## Related Notes

- [[wiki/<domain-id>/<related-note>]]

## Caveats and Follow-up

- Known uncertainty:
- Next review trigger:
```

## Cross-Domain Concept

```markdown
---
title: <concept>
kb_stage: wiki
bucket: concepts
source_refs:
  - wiki/<domain-a>/<source-page>.md
  - wiki/<domain-b>/<source-page>.md
related_notes:
  - wiki/<domain-a>/<source-page>.md
  - wiki/<domain-b>/<source-page>.md
last_reviewed: <YYYY-MM-DD>
status: active
path_base: knowledge_root
---

# <Concept>

## Definition

## Domain-Specific Variations

| Domain | Meaning or behavior | Source |
| --- | --- | --- |
|  |  |  |

## Shared Rules

## Open Differences
```

## Stable Q&A Archive

```markdown
---
title: <archive-topic>
kb_stage: wiki
bucket: archives
source_refs:
  - <source-note-path>
related_notes:
  - <related-wiki-page>
last_reviewed: <YYYY-MM-DD>
status: archived
path_base: knowledge_root
---

# <Archive Topic>

## Why This Is Reusable

## Sources

## Archived Conclusion

## Reuse Guidance
```

## Approved Execution Plan

```markdown
---
title: <execution-plan-topic>
kb_stage: plan
bucket: <domain-id>
source_refs:
  - <approved-spec-or-artifact>
related_notes:
  - <related-wiki-page>
last_reviewed: <YYYY-MM-DD>
status: approved
path_base: knowledge_root
---

# <Execution Plan>

## Goal

## Scope

## Preconditions and Dependencies

## Execution Steps

## Validation and Regression

## Risks and Follow-up
```

## Health Check

```markdown
---
title: <scope-health-check>
kb_stage: health-check
bucket: vault
source_refs: []
related_notes:
  - <page-under-review>
last_reviewed: <YYYY-MM-DD>
status: baseline
---

# <Scope> Health Check

## Summary

## Findings

| Category | Affected Pages | Impact | Suggested Repair | Suggested Evidence |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## Recommended Next Actions
```
