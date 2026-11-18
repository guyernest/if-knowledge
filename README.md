# Interactive Fiction Knowledge

Community-authored knowledge for interactive fiction games, in Open Knowledge
Format (OKF). This repository is the content source for GraphRAG builds used by
interactive fiction assistants. It is independent of the game engine and MCP app.

The initial collection contains three opening hints and one location observation
for **Lost Pig**, plus an empty **Zork I** starter bundle. These are original,
machine-checked drafts awaiting human review. There are no complete maps,
walkthroughs, images, game binaries, or generated GraphRAG snapshots yet.

## Browse and contribute

Start at the [collection index](okf/index.md). Each game has its own directory
under `okf/`, and [catalog.json](catalog.json) records its exact story SHA-256.
Coverage is specific to that story version; an empty bundle means no coverage.

See [CONTRIBUTING.md](CONTRIBUTING.md) for authoring, sources, spoiler levels,
validation, and adding a game. Contributions of hints, maps, walkthroughs, and
images are welcome when the contributor has the rights to share them.

## Validate

Python 3.10 or later is required. No game binaries or app checkout are needed.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/validate.py
.venv/bin/python -m unittest discover -s tests
```

To also check the actual platform ingestion output, supply an `okf-ingest` binary
built from the GraphRAG platform workspace:

```sh
.venv/bin/python scripts/validate.py --ingester /path/to/okf-ingest
```

GitHub Actions runs content checks and validator tests on pull requests and
pushes. Real ingestion is an additional local/platform check requiring that binary.
Interpreter and story-binary checks remain in the
[MCP app repository](https://github.com/guyernest/MCP-IF).

Pull requests are also checked by the platform's own engine, `okf-check`, which
posts a preview comment with the findings (the workflow is `okf-check`; its
maintainer setup is in [.github/okf/CI.md](.github/okf/CI.md)). It needs no
setup from contributors.

## Add a game or a hint

```sh
# a new game: creates the catalog entry and an empty okf/<id>/ bundle
.venv/bin/python scripts/new_game.py zork2 --title "Zork II" --story-sha256 <sha256 of the story file>
```

Hints and places start from the files in [templates/](templates/README.md).

## Publish to the platform

Maintainers can publish `okf/` straight from this repository to the platform instance
bound to it: run the **okf-publish** workflow (Actions, Run workflow, branch `main`).
It stages the bundle, starts the platform's build and stops at "awaiting approval";
an administrator reviews the quality report and approves in the platform admin. The
workflow can only run from `main` and needs no stored credential (it uses GitHub's
OIDC token). Settings and the trust model are in the header of
[.github/workflows/okf-publish.yml](.github/workflows/okf-publish.yml).

## Build a GraphRAG service

Configure your existing repository-based builder with:

| Setting | Value |
| --- | --- |
| Repository | `https://github.com/guyernest/if-knowledge` |
| Bundle directory | `okf/` for all games, or `okf/lost-pig/` for one game |
| Revision | An explicitly selected commit SHA |

`okf/index.md` is the collection entry point for builders accepting one bundle
directory. The platform CLI also accepts multiple game roots explicitly:

```sh
/path/to/okf-ingest okf/lost-pig okf/zork1 /tmp/if-knowledge-normalized
```

Record the source commit in the resulting build/deployment metadata. To reproduce
a build, check out that commit before ingestion. This repository does not create
or deploy a GraphRAG service automatically. Consumers keep their own approved
document allowlists, routing, credentials, and deployment configuration.

## Spoilers and incomplete coverage

The repository itself contains spoilers. Hint tiers are separate documents:
`hint-1` is gentle, `hint-2` is guided, and `hint-3` is explicit. Tags describe
content; they do not provide access control. In particular, unrestricted search,
index documents, graph neighbors, and citations can expose other tiers or games.

Consumers must resolve the active story version, player context, and requested
assistance level before selecting approved documents. They must also enforce
map discovery separately. Missing coverage should produce an unavailable answer,
not invented game facts. Passing validation does not certify facts or spoiler safety.

## License and attribution

Original content and catalog metadata are licensed under **CC BY 4.0**; validation
code, tests, and workflow configuration use **MIT**. See [LICENSE](LICENSE) and
[LICENSE-CODE](LICENSE-CODE). Credit the IF Knowledge contributors and link to
the source revision; preserve any additional attribution provided with an asset.
Game names identify their respective games. No license to the games themselves
is granted by this repository.
