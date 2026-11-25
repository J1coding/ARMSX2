#!/usr/bin/env python3
"""iOS changelog, stage 0: no LLM. Turn a git range into compact, chunked
digests of the commits that matter to iOS players.

  collect.py run BASE [--end upstream/master] [--remote upstream]
                      [--chunk 150] [--out DIR] [--no-fetch]
  collect.py check DIR

`run` fetches the end branch (remote-tracking refs only), lists the non-merge
commits in BASE..END, classifies each by the paths it touches, drops what iOS
players cannot feel, and writes DIR/work/chunk-NN.txt for the summarising
workers plus DIR/work/manifest.json and DIR/work/dropped.tsv.

`check` compares the workers' DIR/work/out-NN.json files with the manifest and
lists kept commits that no worker accounted for.

See .claude/skills/ios-changelog/SKILL.md for the whole pipeline.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
from collections import Counter

BODY_CAP = 240
SEP_REC, SEP_FLD, SEP_END = "\x1e", "\x1f", "\x1d"

# --- path rules -------------------------------------------------------------
# iOS-only places a player can feel.
IOS_PREFIXES = ("platforms/ios/", "pcsx2/GS/Renderers/Metal/")
# Inside platforms/ios but not part of the app a player runs.
IOS_INTERNAL = (
    "platforms/ios/scripts/", "platforms/ios/docs/", "platforms/ios/tools/",
    "platforms/ios/patches/", "platforms/ios/app/src/main/tests/",
    "platforms/ios/README", "platforms/ios/BUILD_WINDOWS.md",
)
# Shared core that also runs on iOS.
SHARED_PREFIXES = ("pcsx2/", "common/", "bin/resources/", "3rdparty/")
# Dropped, with the reason shown in the report.
DROP_RULES = (
    ("android-only", ("platforms/android/",)),
    ("desktop-only", ("pcsx2-qt/", "pcsx2-gsrunner/", "pcsx2-sdl/", "pcsx2-libretro/",
                      "pcsx2/x86/", "bin/translations/",
                      "pcsx2/Linux/", "pcsx2/Windows/", "common/Linux/", "common/Windows/",
                      "pcsx2/Recording/", "pcsx2/Debugger/")),
    # Big Picture (ImGui FullscreenUI); iOS menus are SwiftUI. The OSD and
    # overlays in pcsx2/ImGui/ are NOT dropped.
    ("bigpicture-ui", ("pcsx2/ImGui/FullscreenUI",)),
    ("other-renderer", ("pcsx2/GS/Renderers/Vulkan/", "pcsx2/GS/Renderers/OpenGL/",
                        "pcsx2/GS/Renderers/DX11/", "pcsx2/GS/Renderers/DX12/",
                        "pcsx2/GS/Renderers/DX/")),
    ("infra", (".github/", "tests/", "tools/", "docs/", "cmake/", "updater/", "extras/",
               "pcsx2-eerunner/", "pcsx2-vurunner/", ".gitlab-ci.yml", ".git-blame-ignore-revs",
               ".claude/", ".zcode/", ".superpowers/", ".opencode/", ".ai-local/",
               "crowdin.yml", ".clang-format", ".gitignore", ".gitattributes", ".gitmodules",
               ".codacy.yaml", ".prettierrc.yaml", "README", "REFACTOR_STATUS.md",
               "CMakeLists.txt", "CMakePresets.json", "COPYING", "PCSX2_qt.sln")),
)
INFRA_SUFFIXES = (".md", ".vcxproj", ".filters", "CMakeLists.txt")
OTHER_PLATFORM_SUBJECT = re.compile(r"^(Android|macOS|Mac|Linux|Windows|Qt|Desktop)\b[:/ ]", re.I)


def git(*args, check=True):
    r = subprocess.run(["git", "-c", "core.quotepath=off", *args], capture_output=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r.stdout


def file_kind(path):
    """-> ('ios'|'shared'|'drop'|'other', reason)"""
    if path.startswith(IOS_INTERNAL):
        return "drop", "ios-internal"
    if path.startswith(IOS_PREFIXES) or path.endswith(".metal"):
        return "ios", ""
    for reason, prefixes in DROP_RULES:
        if path.startswith(prefixes) or (reason == "infra" and path.endswith(INFRA_SUFFIXES)):
            return "drop", reason
    if path.startswith(SHARED_PREFIXES):
        return "shared", ""
    return "other", ""


def area(path):
    p = path
    if p.startswith("platforms/ios/app/src/main/"):
        p = p[len("platforms/ios/app/src/main/"):]
    return "/".join(p.split("/")[:2])


def classify(subject, files):
    """-> (bucket 'I'|'S'|None, drop_reason, hint)"""
    if not files:
        return None, "empty", ""
    kinds = [file_kind(f) for f in files]
    hint = "android-labelled" if OTHER_PLATFORM_SUBJECT.match(subject) else ""
    if any(k == "ios" for k, _ in kinds):
        return "I", "", hint
    if any(k == "shared" for k, _ in kinds):
        return "S", "", hint
    reasons = Counter(r for k, r in kinds if k == "drop")
    if reasons:
        return None, reasons.most_common(1)[0][0], ""
    return None, "other", ""


def clean_body(body):
    lines = [l.strip() for l in body.splitlines()]
    lines = [l for l in lines if l and not re.match(r"(Co-Authored-By|Signed-off-by|Generated with)", l, re.I)]
    text = re.sub(r"\s+", " ", " ".join(lines)).replace("|", "/")
    return text[:BODY_CAP] + ("..." if len(text) > BODY_CAP else "")


def resolve_base(base, remote):
    r = subprocess.run(["git", "rev-parse", "--verify", "-q", base + "^{commit}"],
                       capture_output=True, text=True)
    if r.returncode == 0:
        return r.stdout.strip()
    sha = None
    for line in git("ls-remote", "--tags", remote, base, base + "^{}").splitlines():
        s, ref = line.split("\t")
        if ref.endswith("^{}"):
            return s
        sha = sha or s
    if not sha:
        sys.exit(f"cannot resolve base '{base}' locally or on remote '{remote}'")
    return sha


def read_commits(base_sha, end_sha):
    fmt = f"{SEP_REC}%H{SEP_FLD}%cs{SEP_FLD}%s{SEP_FLD}%b{SEP_END}"
    raw = git("log", "--no-merges", "--reverse", "--name-only", "--no-renames",
              "--format=" + fmt, f"{base_sha}..{end_sha}")
    commits = []
    for rec in raw.split(SEP_REC)[1:]:
        head, _, files = rec.partition(SEP_END)
        sha, date, subject, body = head.split(SEP_FLD, 3)
        commits.append({"sha": sha, "date": date, "subject": subject.strip(),
                        "body": clean_body(body),
                        "files": [f for f in files.splitlines() if f.strip()]})
    return commits


def cmd_run(a):
    sys.stdout.reconfigure(encoding="utf-8")
    if not a.no_fetch and "/" in a.end:
        remote, branch = a.end.split("/", 1)
        print(f"fetching {remote} {branch} (no tags)...", flush=True)
        git("fetch", remote, branch, "--no-tags")
    base = resolve_base(a.base, a.remote)
    end = git("rev-parse", a.end + "^{commit}").strip()
    if subprocess.run(["git", "cat-file", "-e", base + "^{commit}"]).returncode != 0:
        sys.exit(f"base commit {base[:10]} is not in the local repo; fetch it first")
    if subprocess.run(["git", "merge-base", "--is-ancestor", base, end]).returncode != 0:
        sys.exit(f"base {base[:10]} is not an ancestor of {end[:10]}")

    commits = read_commits(base, end)
    subjects = {c["subject"] for c in commits}
    reverted = {m.group(1) for s in subjects if (m := re.match(r'Revert "(.+)"$', s))}
    kept, dropped, other_dirs = [], [], Counter()
    for c in commits:
        bucket, reason, hint = classify(c["subject"], c["files"])
        m = re.match(r'Revert "(.+)"$', c["subject"])
        # a revert whose target is in range, and the target itself: both vanish
        if (m and m.group(1) in subjects) or c["subject"] in reverted:
            bucket, reason = None, "reverted"
        c.update(bucket=bucket, reason=reason, hint=hint)
        if reason == "other":
            other_dirs.update(area(f) for f in c["files"])
        (kept if bucket else dropped).append(c)

    out = os.path.abspath(a.out or f"docs/changelog/ios-{a.base}-to-{end[:7]}")
    work = os.path.join(out, "work")
    os.makedirs(work, exist_ok=True)
    for old in glob.glob(os.path.join(work, "chunk-*.txt")):
        os.remove(old)

    n_chunks = 0
    for i in range(0, len(kept), a.chunk):
        n_chunks += 1
        lines = []
        for c in kept[i:i + a.chunk]:
            areas = ",".join(x for x, _ in Counter(area(f) for f in c["files"]).most_common(2))
            line = f"{c['sha'][:7]} {c['bucket']} {c['subject']}"
            if c["hint"]:
                line += f" [{c['hint']}]"
            line += f" @ {areas}"
            if c["body"]:
                line += f" :: {c['body']}"
            lines.append(line)
        with open(os.path.join(work, f"chunk-{n_chunks:02d}.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    with open(os.path.join(work, "dropped.tsv"), "w", encoding="utf-8") as f:
        for c in dropped:
            f.write(f"{c['sha'][:7]}\t{c['reason']}\t{c['subject']}\n")
    counts = Counter(c["reason"] for c in dropped)
    manifest = {"base": a.base, "base_sha": base, "end": a.end, "end_sha": end,
                "total": len(commits), "chunks": n_chunks,
                "kept": [{"sha": c["sha"][:7], "b": c["bucket"], "subject": c["subject"]} for c in kept],
                "dropped": dict(counts)}
    with open(os.path.join(work, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)

    print(f"base {a.base} {base[:10]} -> end {a.end} {end[:10]}")
    print(f"range: {len(commits)} non-merge commits")
    print(f"kept {len(kept)}  (iOS {sum(c['bucket'] == 'I' for c in kept)}, "
          f"shared {sum(c['bucket'] == 'S' for c in kept)}, "
          f"android-labelled hint {sum(bool(c['hint']) for c in kept)})")
    print("dropped " + str(len(dropped)) + "  " + ", ".join(f"{r}={n}" for r, n in counts.most_common()))
    if other_dirs:
        print("unclassified paths (tune DROP_RULES / SHARED_PREFIXES):",
              ", ".join(f"{d}={n}" for d, n in other_dirs.most_common(12)))
    print(f"{n_chunks} chunks of up to {a.chunk} -> {work}")


def cmd_check(a):
    sys.stdout.reconfigure(encoding="utf-8")
    work = os.path.join(a.dir, "work")
    manifest = json.load(open(os.path.join(work, "manifest.json"), encoding="utf-8"))
    kept = {k["sha"]: k for k in manifest["kept"]}
    seen = Counter()
    n_items = n_skipped = 0
    for p in sorted(glob.glob(os.path.join(work, "out-*.json"))):
        d = json.load(open(p, encoding="utf-8"))
        for it in d.get("items", []):
            n_items += 1
            seen.update(s[:7] for s in it.get("shas", []))
        for sk in d.get("skipped", []):
            n_skipped += 1
            seen.update(s[:7] for s in sk.get("shas", []))
        seen.update(s[:7] for s in d.get("unsure", []))
    orphans = [k for s, k in kept.items() if s not in seen]
    unknown = [s for s in seen if s not in kept]
    print(f"kept {len(kept)}; covered {len(kept) - len(orphans)}; items {n_items}; skipped groups {n_skipped}")
    if unknown:
        print("shas in worker output that are not in the manifest:", " ".join(unknown))
    for k in orphans:
        print(f"ORPHAN {k['sha']} {k['b']} {k['subject']}")
    sys.exit(1 if orphans or unknown else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("base")
    r.add_argument("--end", default="upstream/master")
    r.add_argument("--remote", default="upstream")
    r.add_argument("--chunk", type=int, default=150)
    r.add_argument("--out")
    r.add_argument("--no-fetch", action="store_true")
    r.set_defaults(fn=cmd_run)
    c = sub.add_parser("check")
    c.add_argument("dir")
    c.set_defaults(fn=cmd_check)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
