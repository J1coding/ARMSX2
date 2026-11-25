#!/usr/bin/env python3
"""iOS changelog, stage 3: split a finished changelog.md into Discord messages.

  split_discord.py changelog.md [-o discord-messages.md] [--limit 2000]

Input shape: `# Title`, optional intro paragraphs, then `## Section` headings,
each followed by items separated by blank lines. Messages are packed greedily
at item boundaries. A section that spans messages gets `## Name (cont.)`.
Exits non-zero if anything is over the limit or the markdown looks broken.
"""
import argparse
import re
import sys


def u16(s):
    """Discord counts UTF-16 code units, like JavaScript string length."""
    return len(s.encode("utf-16-le")) // 2


def parse(text):
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    if not blocks or not blocks[0].startswith("# "):
        sys.exit("first block must be a '# Title' line")
    title, sections = blocks[0], [[None, []]]
    for b in blocks[1:]:
        if b.startswith("## "):
            sections.append([b[3:].strip(), []])
        else:
            sections[-1][1].append(b)
    return title, [(s, i) for s, i in sections if i]


def pack(title, sections, limit):
    msgs, cur, in_cur, emitted = [], title, None, set()
    if u16(title) > limit:
        sys.exit("title alone is over the limit")
    for sec, items in sections:
        for item in items:
            def piece():
                if sec is None or in_cur == sec:
                    return item
                return f"## {sec}{' (cont.)' if sec in emitted else ''}\n\n{item}"
            cand = f"{cur}\n\n{piece()}" if cur else piece()
            if u16(cand) > limit:
                if cur:
                    msgs.append(cur)
                cur, in_cur = "", None
                cand = piece()
                if u16(cand) > limit:
                    sys.exit(f"one item is over {limit} chars ({u16(cand)}): {item[:70]}...")
            cur = cand
            if sec is not None:
                in_cur = sec
                emitted.add(sec)
    if cur:
        msgs.append(cur)
    return msgs


def problems(msgs, limit):
    bad = []
    for n, m in enumerate(msgs, 1):
        if u16(m) > limit:
            bad.append(f"message {n}: {u16(m)} chars")
        if m.count("**") % 2:
            bad.append(f"message {n}: unbalanced **")
        if re.search(r"[–—]", m):
            bad.append(f"message {n}: contains an em or en dash")
        if re.search(r"(?<![\w<])@\w", m) or re.search(r"<@", m):
            bad.append(f"message {n}: contains an @ mention")
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("-o", "--out")
    ap.add_argument("--limit", type=int, default=2000)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    title, sections = parse(open(a.src, encoding="utf-8").read())
    msgs = pack(title, sections, a.limit)
    out = a.out or re.sub(r"[^/\\]+$", "discord-messages.md", a.src)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        for n, m in enumerate(msgs, 1):
            f.write(f"===== MESSAGE {n}/{len(msgs)} · {u16(m)} chars =====\n{m}\n\n")
    sizes = [u16(m) for m in msgs]
    print(f"{len(msgs)} messages, {min(sizes)}-{max(sizes)} chars (limit {a.limit}) -> {out}")
    bad = problems(msgs, a.limit)
    for b in bad:
        print("PROBLEM", b)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
