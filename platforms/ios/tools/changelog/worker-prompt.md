# Worker prompt: summarise one chunk of commits

You turn one chunk of git commits for ARMSX2 (a PlayStation 2 emulator; this is the iOS app) into short, player-facing change items. Do not run git, do not read the repository. Read only the chunk file you were given, write only the output file you were given.

## Input

You may get several CHUNK/OUT pairs. Handle each pair on its own: read one chunk, write its own output file, and account for every sha of that chunk in that chunk's file only.

The chunk file has one commit per line:

`sha7 B subject [hint] @ area1,area2 :: body`

- `B` is `I` (iOS app or Metal code) or `S` (shared emulator core that also runs on iOS).
- `[android-labelled]` means the subject names another platform. Keep it only if the text clearly says it applies to every platform, otherwise skip it with why `other-platform`.
- `@ areas` are the top folders the commit touched. They are a hint for cryptic subjects.
- Commits are in time order. A later commit may fix or revert an earlier one in the same chunk; describe the end result, not the back and forth.

## Output

Write one JSON file:

```json
{
  "items": [{"cat": "graphics", "title": "Short headline", "text": "One or two plain sentences.", "shas": ["abc1234", "def5678"]}],
  "skipped": [{"shas": ["abc1234"], "why": "internal"}],
  "unsure": ["abc1234"]
}
```

Every sha in the chunk must appear exactly once across `items[].shas`, `skipped[].shas` and `unsure`.

## Rules for items

- Merge commits that are about the same thing into one item.
- `title`: 3 to 8 words, plain, no trailing period needed (it becomes a bold lead).
- `text`: one or two sentences. Say what the player sees or what stopped going wrong. Use game names, numbers and settings names only if they are in the commit text. Never invent them.
- No em or en dashes. No SHAs, no file names, no function names, no "refactor". Plain words a player knows. Skip jargon like JIT, microVU, VIF, TLB unless you can say what it does for the player, for example "games run faster".
- `cat`, pick the closest: `controls`, `menus`, `graphics`, `speed`, `accuracy`, `games`, `audio`, `saves`, `settings`, `achievements`, `fixes`, `new`, `other`.
- `skipped` is for things a player will never notice: refactors, logging, build or CI changes, tests, version bumps, translations syncs, comments, code moves, internal tooling. Use `why`: `internal`, `build`, `tests`, `reverted`, `other-platform`, `no-effect`.
- If you cannot tell what a commit does for a player from its text, put its sha in `unsure`. Do not guess.

Reply with one line only: `done: N items, M skipped, K unsure`.
