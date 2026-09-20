# AGENTS.md

## Repository purpose

This repository stores public, reusable agent skills. Skills must be independently usable and must not assume access to private repositories, internal services, company-specific tools, or unpublished business context.

## Structure

```text
skills/
  <kebab-case-name>/
    SKILL.md
    references/
    evals/
```

- Keep `SKILL.md` as the execution contract.
- Put heavy reference material in `references/`.
- Put realistic trigger and behavior tests in `evals/evals.json`.
- Add only files required by the skill.

## Skill requirements

- Frontmatter must contain `name` and `description`.
- `name` must match the directory name.
- `description` must start with `Use when` and describe triggering conditions, not summarize the workflow.
- State local runtime dependencies or explicitly say that there are none.
- Use relative links and verify every referenced file exists.
- Keep examples fictional and organization-neutral unless they have documented publication approval.

## Publication safety

Passing sensitive-content checks is not permission to publish or closely adapt private source wording, examples, structure, selection, or arrangement. Reuse requires documented authorization from the party that actually holds the relevant public-redistribution and adaptation rights; an employer name alone is not evidence of ownership.

Never publish:

- credentials, tokens, cookies, keys, connection strings, or private endpoints;
- internal organization, system, repository, module, branch, commit, deployment, or ownership identifiers;
- non-public business processes, data definitions, state models, incidents, or operating schedules;
- third-party text, translations, diagrams, or cases without documented redistribution or quotation rights.

If only part of an item fails review, change or remove only that part. Do not rewrite approved content by default. Do not commit sensitive rejection evidence to this public repository.

When using the independent synthesis path, keep factual attribution and source links in the relevant reference page, but create a new method structure and original cases.

## Change safety

- Prefer local, additive changes.
- Do not normalize unrelated skills.
- Do not add cross-skill dependencies unless the referenced public skill exists.
- Describe optional follow-on capabilities by role when no public skill exists.
- Verify trigger boundaries, references, sensitive terms, and independent usability before handoff.
