# Knowledge-base repository CI runbook

This runbook is for the maintainers of a knowledge-base (KB) repository created from this template. It explains what the vendored workflows do, the one-time setup (in the order that avoids red first runs), the repository settings the security model depends on, and how to seed, bump, recover and rotate the pinned `okf-check` engine.

Terms: the *default branch* is the branch the repository's Pull Requests merge into; the *engine* is the `okf-check` binary pinned in `.okf/engine.lock`; the *release repository* is the private repository whose releases carry that binary.

## 1. What runs

| Workflow | Trigger | What it does |
| --- | --- | --- |
| `okf-check` | every pull request | The **required check**. Restores the pinned engine from the Actions cache, runs `okf-check check` and `okf-check preview` against the pull request, writes the job summary and annotations, and uploads the comment text. It holds no secret and no write token, and it never downloads: a cache miss fails closed. Its job is named `okf-check`; that is the status name the branch ruleset requires. |
| `okf-preview-comment` | `okf-check` completed | The **poster**. Reads the uploaded comment as data, proves it belongs to exactly one open pull request, re-validates it and creates or updates one sticky comment. A posting failure never fails the check, and this workflow is never a required check. It only exists for GitHub once its file is on the default branch. |
| `okf-seed-engine` | push to the default branch, twice a week, manual | The **only** workflow that holds the engine read token. Downloads the pinned engine from the release repository, verifies it against the lock and saves it to the Actions cache. Runs inside the `okf-engine-seed` environment. |
| `okf-bundle-view` | after a successful `okf-seed-engine` on the default branch, manual | Builds the bundle view (a static page with the documents, links and trust tiers, metadata only) and keeps it as the `bundle-view` artifact for 30 days. |
| `okf-pages` | manual only, off by default | Optionally publishes the bundle view to GitHub Pages. Does nothing unless you opt in (section 8). |

Two composite actions back them: `okf-engine` (restore or seed the pinned engine and prove its checksum and version) and `okf-check` (the pull-request check script). Workflows run inline scripts; none of them depends on `just`.

## 2. Prerequisite: your plan must support environment secrets

The engine token is stored as a secret of the `okf-engine-seed` **environment**, and that environment restricts which branches may use it. In a **private** repository, environment secrets and deployment-branch policies need GitHub Pro (a personal account) or GitHub Team or Enterprise (an organisation). On GitHub Free, either use a public repository or upgrade. Never fall back to a repository secret: a repository secret is readable by workflows from every branch and would defeat the design.

## 3. First-time setup, in this order

The secret must exist before anything runs, so that the first seed and view runs succeed. Replace `<owner>/<repo>` with the KB repository and `<default>` with its default branch name.

1. **Create the repository** from the template.

2. **Create the environment `okf-engine-seed`** (Settings, Environments, New environment) and restrict its deployment branches: Deployment branches and tags, Selected branches and tags, add the default branch name, and no tag rule. With the CLI:

   ```bash
   gh api -X PUT repos/<owner>/<repo>/environments/okf-engine-seed \
     -F 'deployment_branch_policy[protected_branches]=false' \
     -F 'deployment_branch_policy[custom_branch_policies]=true'
   gh api -X POST repos/<owner>/<repo>/environments/okf-engine-seed/deployment-branch-policies \
     -f name=<default> -f type=branch
   ```

3. **Create `ENGINE_RELEASE_TOKEN`**: a fine-grained personal access token owned by the **release repository's owner** (which may be a different organisation from this repository's), with Repository access set to only the release repository, the Contents permission set to read-only, and an explicit expiry within your organisation's policy. Record the expiry date in the repository's notes so the rotation (section 7) happens before it. Store it **only** as that environment's secret:

   ```bash
   gh secret set ENGINE_RELEASE_TOKEN --env okf-engine-seed --repo <owner>/<repo>
   ```

   Do not create a repository-level secret with that name. Check with `gh secret list --repo <owner>/<repo>`: the name must not appear there.

4. **Name the maintainers.** Replace `@OKF_MAINTAINERS` in `.github/CODEOWNERS` with your maintainer team or user (CODEOWNERS only protects anything once both this and the ruleset in section 4 are done). List maintainer logins in `.okf/maintainers`, one per line: only a listed author of type User gets human-stamp and profile-configuration changes downgraded from errors to warnings (D-10). The copy on the default branch is the one that counts, so a pull request cannot add its own author.

5. **Set the optional repository variables** (Settings, Secrets and variables, Actions, Variables): `OKF_BUNDLE_PATH` (the bundle directory, default `bundle`) and `OKF_RUNNER` (the runner label, default `ubuntu-latest`).

6. **Commit the template to the default branch.** Make sure `.okf/engine.lock` holds the pin copied from the engine release's `engine.lock` first. The push runs `okf-seed-engine`; its success runs `okf-bundle-view`, and from this commit on the poster workflow exists for GitHub.

7. **Confirm** the `okf-seed-engine` and `okf-bundle-view` runs are green (Actions tab) before opening any pull request.

8. **Add the branch ruleset** on the default branch (section 4).

## 4. Required settings

Repository settings, under Settings, Actions, General:

| Setting | Value |
| --- | --- |
| Run workflows from fork pull requests | On |
| Send write tokens to workflows from fork pull requests | Off |
| Send secrets to workflows from fork pull requests | Off |
| Require approval for fork pull request workflows | Your policy |

Private repositories default to *not* running workflows for fork pull requests, which leaves a fork's required `okf-check` status pending forever; turn the first row on. The check needs no secret and no write token, so the next two rows stay off: fork pull requests are validated without either. Approval for fork workflows is your choice; with it on, the required check waits until a maintainer approves the run.

Branch ruleset on the default branch (Settings, Rules, Rulesets):

- Require a pull request before merging.
- Require the status check **`okf-check`** (never `okf-preview-comment`; the poster is best effort and not a gate).
- **Require review from Code Owners.** The `okf-engine-seed` environment trusts the default branch, so the ruleset is what keeps unreviewed code off it. A pull request can edit the workflow and actions it runs from; the code-owner review of `.github/` and `.okf/` is the control for that, and the job summary says when a change touches them.

Environment `okf-engine-seed`:

- Deployment branches: the default branch only.
- No repository-level secret named `ENGINE_RELEASE_TOKEN` exists.

## 5. Bumping the engine pin

A pull request never downloads (so a pin change cannot reach the token), which means a pin-bump pull request stays red until the new engine is seeded. This is by design.

1. Download `engine.lock` from the new engine release.
2. Open a pull request replacing `.okf/engine.lock` (code-owner review applies).
3. Dispatch **okf-seed-engine** on the default branch (Actions, okf-seed-engine, Run workflow) with `lock-ref` set to the pull request's branch name, or `pull/<N>/head` for a pull request from a fork. The job reads that ref's `.okf/engine.lock` as data only and seeds it, provided its `release_repo` equals the default branch's; a candidate that changes the release repository is refused, so land that change on the default branch first.
4. Re-run the pull request's `okf-check`. It restores the seeded entry and passes.
5. Merge. The push to the default branch seeds the same pin again (a cache hit that refreshes the entry).

## 6. Troubleshooting

| Symptom | Meaning and fix |
| --- | --- |
| `engine not seeded for <version>` | The cache has no entry for the pinned engine. Run the Seed workflow on the default branch. For a pin-bump pull request, dispatch it with `lock-ref` (section 5). |
| `okf-check binary sha256 mismatch` | The lock or the cache entry is wrong. Re-check `.okf/engine.lock` against the `engine.lock` of the release it names; if the lock is right, remove the entry (next row) and re-seed. |
| An invalid cache entry fails every restore | List the entries with `gh cache list --key okf-engine-v1-`, remove the bad one with `gh cache delete <key>`, then dispatch `okf-seed-engine`. |
| `checksums.txt disagrees with .okf/engine.lock` | Stop. The release does not match the pin. Contact the engine owner; do not edit the lock to match. |
| `could not download` in the seed | The token expired, belongs to the wrong owner, or lacks Contents read on the release repository. Rotate it (section 7). |
| The seed job fails with an environment-protection message | It ran from a ref other than the default branch (expected for any other branch), or the environment's deployment-branch policy names the wrong branch. Fix the policy (section 3, step 2). |
| No comment appears on a pull request | The poster file must be on the default branch (it exists for GitHub only from there). Two open pull requests sharing one head branch get no comment, by design. A comment failure never fails the check; read the `okf-preview-comment` run. |
| Trusted review was not applied | The author is not listed in `.okf/maintainers` **on the default branch**, the file is invalid (the job summary names the warning), or the author is a bot. |
| A scheduled seed stopped | GitHub disables scheduled workflows after 60 days without repository activity in **public** repositories: re-enable the workflow. Private repositories are unaffected, and every default-branch push seeds again. |
| `okf-seed-engine` is skipped on a branch push | Expected and free: only default-branch pushes run it. |
| A fork pull request's check stays pending | Fork workflows are disabled, or awaiting approval. Turn on "Run workflows from fork pull requests" or approve the run. Do not fix a pending or red check by sending secrets or write tokens to forks: the check needs neither, and enabling either exposes the repository to every fork. |

## 7. Rotating the engine token

A warm cache never uses the token, so the rotation has to force a download with the new one. An expired token only breaks seeding; warm pull request runs keep working.

1. Create the new fine-grained token (section 3, step 3).
2. Update the environment secret: `gh secret set ENGINE_RELEASE_TOKEN --env okf-engine-seed --repo <owner>/<repo>`.
3. Delete the current cache entry for your runner's architecture: `gh cache delete okf-engine-v1-<arch>-<version>-<binary sha256>` (the key is printed by every seed run summary and by `gh cache list --key okf-engine-v1-`). Do this when no pull request is waiting: their checks are red until the next step finishes.
4. Dispatch **okf-seed-engine** and wait for success. The seed had to download, so it used the new token.
5. Only then revoke the old token.

If the seed fails, put the old token back (step 2) and dispatch again.

## 8. Opting into Pages

The bundle view is available as an artifact without Pages. To publish it: set the repository variable `OKF_PAGES_PUBLISH` to `true`, set Settings, Pages, Source to GitHub Actions, then run **okf-pages** by hand. Warning: the Pages site of a private repository may be publicly reachable unless your plan supports private Pages. The view holds document metadata only (titles, paths, trust tiers, links), no document bodies, but that is still the shape of your knowledge base. Leave `OKF_PAGES_PUBLISH` unset to keep it off.
