# Document templates

Copy a file into `okf/<game-id>/hints/` (or `places/`), rename it with the game id
prefix (for example `zork1-mailbox-hint-1.md`), then replace the upper-case
placeholders:

| Placeholder | Value |
| --- | --- |
| `GAME_ID` | the id from `catalog.json` (`zork1`) |
| `GAME_TITLE` | the display name (`Zork I`) |
| `TOPIC` | one short lowercase tag for the puzzle or place (`mailbox`) |
| `STORY_SHA256` | the story hash recorded for the game in `catalog.json` |

Link the new file from the section index (copy `section-index.md` for a new
section). These templates live outside `okf/` on purpose, so they are never
validated or ingested. See [CONTRIBUTING.md](../CONTRIBUTING.md) for the rules.
