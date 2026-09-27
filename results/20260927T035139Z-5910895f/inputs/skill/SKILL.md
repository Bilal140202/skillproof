---
name: notes-format-skill
description: Formatting conventions for release notes and changelog files. Rule 4 is deliberately over-broad so the demo suite can measure a real regression.
---
# Release notes formatting

When writing or editing release notes or changelog files:

1. Start the file with an H1 heading: `# Release notes`.
2. Use H2 section headers (`## Highlights`, `## Fixes`, `## Known issues`).
3. Always end the file with this exact footer on its own lines:

   ---
   *Prepared by the release desk*

4. Spell out small numbers in prose: write "forty-two", never "42".
5. Never alter JSON files or code blocks.

Honesty note: rule 4 conflicts with tasks that demand exact numeric output
(e.g. a line reading exactly `Total: 42 items`). That conflict is intentional
— the demo suite measures it as a pass->fail regression, and the committed
dogfood run under `results/` documents the root cause (EVALUATION.md rule 2:
commit the losing runs).
