---
name: ios-changelog
description: Build a player-facing, Discord-ready changelog of every iOS-relevant change since a previous iOS release tag. Use when the user asks for iOS release notes or a changelog since a version (for example `/ios-changelog iOSv2.6.0`).
---

# iOS changelog

Usage: `/ios-changelog <prev-tag> [end-ref]`. End defaults to `upstream/master` (ARMSX2/ARMSX2). The last release tag is the base. The J1coding fork is usually stale; always use `upstream`.

Goal: every user-visible iOS change in `BASE..END`, in plain player language, split into Discord messages of at most 2000 characters, for as few tokens as possible. Scripts filter and split; Haiku workers draft; the orchestrator (you) merges and writes the final voice.

Scripts live in `platforms/ios/tools/changelog/`. Output goes to `docs/changelog/ios-<base>-to-<end7>/` (untracked; never commit unless asked).

## Steps

1. **Filter (no LLM).** `python platforms/ios/tools/changelog/collect.py run <prev-tag>`. It fetches `upstream master --no-tags`, drops Android-only, desktop-only, other-renderer, CI, tests and docs commits, drops revert pairs, and writes `work/chunk-NN.txt`. Report the printed counts to the user (kept, dropped by reason), then carry on. If it prints unclassified paths, fix `DROP_RULES` or `SHARED_PREFIXES` in `collect.py` and rerun.
2. **Draft (cheap workers).** Each subagent carries about 42k tokens of fixed overhead, so use few workers: about 3, each with 2 to 3 chunks, all in one message so they run in parallel (`run_in_background: true`). Use `model: haiku`; if it fails with `model_not_found` (it did on 2026-11-25, the alias pointed at an unavailable model), use `model: sonnet`. Prompt per worker: `Follow platforms/ios/tools/changelog/worker-prompt.md`, then the work directory and the `chunk-NN.txt -> out-NN.json` pairs.
3. **Check coverage.** `python platforms/ios/tools/changelog/collect.py check <out dir>`. Place every ORPHAN (add to an item, or skip with a reason). Repeat until clean.
4. **Resolve `unsure`.** `git show --stat -1 <sha>` and a short diff peek. Budget about 30 commits. Anything still unclear gets dropped, not guessed.
5. **Merge and write** `changelog.md` in the voice below. Merge items across chunks that describe one feature. For items built only from `[android-labelled]` or VU, EE or JIT commits, check the touched files are compiled for iOS; drop the item if not. Group into topic sections ordered by player impact. End with at most one short "under the hood" line.
6. **Split.** `python platforms/ios/tools/changelog/split_discord.py <out dir>/changelog.md`. It must exit 0 (every message at most 2000 characters, balanced `**`, no dashes, no @).
7. **Verify.** Spot check 10 random items against `git show`. Show the user the first message for style sign-off before handing over the file.

## Voice

- `# ARMSX2 for iOS X.Y.Z` (keep the placeholder unless the user gives a version), then `## Topic` sections with names taken from the content.
- Each item: `**Short headline.**` then one to three plain sentences. Say what was wrong and what happens now. Concrete numbers, game names, setting names.
- No credits, handles or pings. No emoji. No em or en dashes. No SHAs or code names. No jargon a player would not know.
- Items stand alone; a message may be read without the ones before it.

Example item: `**Freed textures give their memory back.** Large texture allocations now get memory of their own, which goes back to iOS when the texture is freed.`
