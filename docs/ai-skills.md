# AI Skills and Local Overrides

This repo keeps shared AI workflow instructions in version control so Codex and
Windsurf can use the same project conventions across machines.

## Shared Files

Commit files that describe project-wide behavior:

- `.codex/skills/<skill-name>/SKILL.md`
- `.windsurf/skills/<skill-name>/SKILL.md`
- `.windsurf/workflows/<workflow-name>.md`

Shared files should contain repeatable workflow steps, project conventions, and
safe command guidance. Do not put secrets, personal paths, private account names,
local-only aliases, or machine-specific service URLs in these files.

## Local Overrides

Keep machine-specific notes in ignored local overlays:

- `.codex/skills/<skill-name>.local/SKILL.md`
- `.codex/skills/<skill-name>.local.md`
- `.windsurf/skills/<skill-name>.local/SKILL.md`
- `.windsurf/skills/<skill-name>.local.md`
- `.windsurf/workflows/<workflow-name>.local.md`

Use local overlays for personal environment details such as conda environment
names, private test data, local tunnel URLs, debug commands, or preferred shell
aliases.

When a local override would help other contributors, commit an example file
instead, such as `SKILL.local.example.md`, with placeholders only.

## Review Checklist

Before committing AI skill or workflow changes:

1. Confirm the shared file works without your local machine setup.
2. Move secrets, private URLs, and personal paths into a `.local` overlay.
3. Keep example files placeholder-only.
4. Stage only shared files and examples, never the ignored local overlay.
