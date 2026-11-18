## What this adds or changes

- **Game and story hash** (from `catalog.json`):
- **Topic and spoiler level** (gentle / guided / explicit / observed):
- **Sources** (public URLs, or `urn:sha256:<story-hash>` for your own interpreter observation):
- **How you checked the facts** (steps to reproduce in the exact story version):

## Checklist

- [ ] `python3 scripts/validate.py` and `python -m unittest discover -s tests` pass locally
- [ ] Each hint tier is its own file; gentle hints give no answer in title, description or links
- [ ] The content is original, or I have the right to share it under the repository licenses
- [ ] No story binaries, credentials, generated snapshots or embeddings are included
- [ ] New documents are linked from an index and use `status: unverified`
