# noah-project-skills

Reusable, public agent skills for software engineering work.

## Layout

Each skill lives under `skills/<skill-name>/`:

```text
skills/
  <skill-name>/
    SKILL.md
    references/
    evals/
```

`SKILL.md` is the entry point. Supporting files are loaded only when the task needs them.

## Install

Use a runtime that supports the Agent Skills directory convention.

User-level installation:

```bash
mkdir -p "$HOME/.agents/skills"
cp -R "<repo-root>/skills/software-complexity-design" "$HOME/.agents/skills/"
```

Repository-local installation:

```bash
mkdir -p "<project-root>/.agents/skills"
cp -R "<repo-root>/skills/software-complexity-design" "<project-root>/.agents/skills/"
```

Replace an existing copy when updating. A symlink may be used for local development if the runtime follows symlinks.

## Discovery contract

- The runtime discovers the skill from `software-complexity-design/SKILL.md`.
- The directory name and frontmatter `name` must both be `software-complexity-design`.
- The runtime may index only `name` and `description` before activation.
- `references/` and `evals/` are supporting resources, not separate skills.
- A complete installation copies the whole skill directory so every relative link remains valid.

Verify a user-level installation:

```bash
test -f "$HOME/.agents/skills/software-complexity-design/SKILL.md"
rg '^name: software-complexity-design$' \
  "$HOME/.agents/skills/software-complexity-design/SKILL.md"
```

## Invocation contract

- Automatic use: cross-module, cross-system, or long-running workflow requests where ownership, recovery, boundaries, or future change cost are central.
- Explicit use: ask to “use `software-complexity-design`” for an architecture design or review.
- Non-triggering boundary: class, method, field, SQL, CRUD, or already-decided implementation details.
- The skill produces Markdown guidance and does not require a CLI, credentials, or external service.
- Default output follows the user's language.

## Current scope

- `software-complexity-design`: design and review project architecture, TDD-oriented behavior contracts, cross-system recovery, and incremental evolution of large codebases with an emphasis on controlling change complexity.
- `multi-agent-operate-rule`: coordinate one goal across agents or separate sessions, with fixed input versions, explicit roles, versioned handoffs, and a named resume point.
- `log-and-comment-rule`: add or review focused backend logs and comments across Java, Python, Go, and other languages, following each project's existing logging and documentation conventions.
- `frontend-code-review`: review concrete code changes for correctness, project consistency, reuse, clarity, and the smallest complete delivery.
- `frontend-technical-solution-writer`: draft and review Chinese frontend technical plans covering scope, data contracts, acceptance, and rollback.
- `skill-creator-extra-rules`: create, modify, migrate, or review agent skills with checks for discovery and input/output contracts, runtime dependencies, credentials, behavior evidence, packaging, versioning, and authorized distribution.
- `local-knowledge-agent`: ingest research or Web Clipper material into a local Markdown knowledge base, archive stable Q&A or approved plans, and run health checks along a fixed Clippings → raw → wiki lifecycle.
- `common-decision-assist`: compare, classify, or route finite candidates, score an ordered rubric, or estimate whether a stated proposition holds, using a configured System One-compatible Decision API; returned probabilities are evidence, not calibrated proof.

Install and discovery for `multi-agent-operate-rule` follow the same directory convention:

```bash
mkdir -p "$HOME/.agents/skills"
cp -R "<repo-root>/skills/multi-agent-operate-rule" "$HOME/.agents/skills/"
test -f "$HOME/.agents/skills/multi-agent-operate-rule/SKILL.md"
rg '^name: multi-agent-operate-rule$' \
  "$HOME/.agents/skills/multi-agent-operate-rule/SKILL.md"
```

The directory name and frontmatter `name` must both be `multi-agent-operate-rule`. Automatic use starts when work must be split, handed off, reviewed independently, or resumed across agents. A task one executor can finish, a request to build a scheduler, and merge, deploy, or release approval do not start this skill.

## Contribution rules

1. Keep skills system- and organization-neutral.
2. Do not publish credentials, internal addresses, private business details, or proprietary system identifiers.
3. Public availability alone is not redistribution or adaptation permission. Keep source links near independently written summaries, and do not copy protected expression without compatible permission.
4. Add trigger and behavior evaluations for every skill.
5. Keep root documentation focused on repository intent and maintenance rules rather than a detailed inventory.

## License

Repository-authored content is available under [MIT](LICENSE). Source links and factual attribution do not incorporate the linked works into this repository or relicense their protected expression.
