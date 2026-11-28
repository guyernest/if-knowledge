---
type: Place
title: Zork I Reservoir South route to the Dam
description: A tested short walkthrough between Reservoir South and the Dam.
tags: [game-zork1, navigation, walkthrough]
status: unverified
sources:
  - title: Volunteered interpreter replay of release 119, serial 880429
    resource: urn:sha256:37084966477dff679282de42974b2077156b1bd68fad92a65d4ea94d8eb64d79
---
## Walkthrough

Start in Reservoir South with a light source.

1. Enter `EAST` to reach the Dam.
2. Enter `LOOK` to inspect the location and its controls.
3. Enter `WEST` to return to Reservoir South.

This route is an exploration loop around the closed reservoir. It records movement and observation before using any controls.

```json replay
{"game_id":"zork1","story_sha256":"37084966477dff679282de42974b2077156b1bd68fad92a65d4ea94d8eb64d79","start":{"id":123,"name":"Reservoir South"},"steps":[{"command":"east","location":{"id":178,"name":"Dam"}},{"command":"look","location":{"id":178,"name":"Dam"}},{"command":"west","location":{"id":123,"name":"Reservoir South"}}]}
```
