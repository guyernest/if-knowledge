# Contributing

Use a pull request to add or correct content. Include the game, story hash,
affected topic, intended spoiler level, sources, and how you checked the facts.
Human review is required before calling a draft verified.

## Quick start

- **A new game:** `python3 scripts/new_game.py <game-id> --title "<Title>" --story-sha256 <hash>`
  creates the catalog entry and an empty bundle (steps 1-2 under "Add a game" below).
- **A hint or place:** copy a file from [templates/](templates/README.md), rename it with
  the game ID prefix, fill in the placeholders and link it from an index.
- **Check it:** run the validation commands in the [README](README.md#validate). The pull
  request template lists what a reviewer needs, and the `okf-check` job comments on
  the pull request with the platform engine's findings.

## Author a document

Keep each hint tier in a separate Markdown file so a gentle hint can be returned
without retrieving an explicit solution. Prefix filenames with the game ID:
the ingester derives concept IDs from filenames, and those IDs must be unique
across the collection. Keep hints under 1,100 characters of body text.

For example, `okf/lost-pig/hints/lost-pig-new-topic-hint-1.md`:

```yaml
---
type: Hint
title: Lost Pig new topic hint 1
description: A gentle prompt for the topic, without giving away the solution.
tags: [game-lost-pig, new-topic, hint-1, spoiler-gentle]
status: unverified
sources:
  - title: Observation in the story version recorded in catalog.json
    resource: urn:sha256:7bffe25e933aa22a2b1e9bfc8073bee5687d79a70394da19e50bfed5755368c4
---
```

Add the hint below the frontmatter and link it from the game's index or relevant
section index. The other levels use exactly one `hint-2` or `hint-3` tag, with
`spoiler-guided` or `spoiler-explicit`, respectively. Do not put an answer in a
gentle hint's title, description, links, or source labels.

All documents need `type`, `title`, and `description`. Concept documents also
need `tags`, `status`, and nonempty `sources`. Use `type: Index` for navigation;
other supported platform types include `Hint` and `Place`. Preserve the
`game-<game-id>` tag on each game's documents, including indexes. Use Markdown
links relative to the current document and keep them inside `okf/`.

Use `status: unverified` for a draft. A maintainer may mark independently reviewed
content `stable` after the facts and story applicability have been checked. Tags
and review status are metadata, not an application's permission boundary.

## Sources, maps, images, and walkthroughs

Write original explanations. Do not copy game prose, another person's walkthrough,
or an image without permission to distribute it under this repository's license.
Use public source URLs or `urn:sha256:<story-hash>` to identify interpreter
observations; do not point at a file in a private app checkout. Explain the
reproduction steps and exact story hash in the pull request.

Keep walkthroughs and maps visibly separate from gentle hints. A map should
distinguish observed landmarks from tested exits; an apparent direction is not
proof of a walkable route. Include author, source, license, and attribution for
any image or other asset, and link it from a Markdown document. Never add story
binaries, credentials, deployment output, or generated embeddings/snapshots.

## Add a game or extend coverage

1. Choose a unique game ID and add an entry to `catalog.json`, including the
   title, exact story SHA-256, and `okf/<game-id>` bundle path.
2. Create `okf/<game-id>/index.md` with `type: Index` and the game tag. Link it
   from `okf/index.md`.
3. Add documents and section indexes as needed. Empty bundles are allowed, and
   existing starter bundles can be extended without changing the validator.
4. Run the validation and test commands in the README. If available, also run
   the real ingester check. Fact checks requiring game binaries belong in your
   local game/app environment, not in this repository's public CI.

Changes in this repository do not automatically update a consumer's approved
hint routing or deployed content revision. App maintainers review and adopt a
specific commit separately.

## Contribution licenses

By submitting a contribution, you agree to license your original content under
CC BY 4.0 and your code under MIT, as described in LICENSE and LICENSE-CODE.
Preserve existing attribution and note any changes to third-party material.
