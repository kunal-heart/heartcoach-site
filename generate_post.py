#!/usr/bin/env python3
"""
HeartCoach Insights — automated draft generator.

Pops the next topic from queue.txt, asks Claude (with web search, so it finds and
cites real sources) to draft it using content-agent.md as the system prompt, and
writes a DRAFT to posts/YYYY-MM-DD-slug.md.

The draft always has `reviewed_by:` blank, so build.py will NOT publish it until a
human reviews and fills that field. The agent drafts; a human ships.

Usage:
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-ant-...
    python generate_post.py                    # draft next topic from queue.txt
    python generate_post.py --topic "..." --audience patient   # ad-hoc topic
    python generate_post.py --dry-run          # no API call; writes a stub (for testing plumbing)

Queue format (queue.txt), one topic per line:
    b2b | The economics of patient retention for a cardiology practice
    patient | Small daily walks: the most underrated heart habit
"""

import argparse
import datetime as dt
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).parent
AGENT = ROOT / "content-agent.md"
QUEUE = ROOT / "queue.txt"
QUEUE_DONE = ROOT / "queue-done.txt"
POSTS_DIR = ROOT / "posts"

MODEL = "claude-sonnet-5"           # verified current model (Aug 2026)
WEB_SEARCH = {"type": "web_search_20250305", "name": "web_search", "max_uses": 6}
MAX_TOKENS = 4000


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)[:60]


def next_from_queue():
    if not QUEUE.exists():
        sys.exit("queue.txt not found and no --topic given. Add topics or pass --topic.")
    lines = [l for l in QUEUE.read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.strip().startswith("#")]
    if not lines:
        sys.exit("queue.txt is empty. Add more topics (or the calendar has run dry).")
    first, rest = lines[0], lines[1:]
    if "|" not in first:
        sys.exit(f"Malformed queue line (need 'audience | title'): {first!r}")
    audience, title = (p.strip() for p in first.split("|", 1))
    return audience, title, rest


def pop_queue(remaining, done_line):
    QUEUE.write_text(("\n".join(remaining) + "\n") if remaining else "", encoding="utf-8")
    with QUEUE_DONE.open("a", encoding="utf-8") as f:
        f.write(f"{dt.date.today().isoformat()} | {done_line}\n")


def build_user_prompt(audience, title):
    return (
        f"Draft today's HeartCoach Insights post.\n\n"
        f"Track: {'B2B (cardiovascular organizations / practice decision-makers)' if audience=='b2b' else 'Patient & caregiver (heart patients 55+ and families)'}\n"
        f"Working title: {title}\n"
        f"Today's date: {dt.date.today().isoformat()}\n\n"
        f"Follow content-agent.md exactly. Use web search to find and verify every "
        f"statistic against a real, linkable source, and put those sources in the "
        f"frontmatter `sources:` list. Leave `reviewed_by:` blank.\n\n"
        f"Output ONLY the finished markdown file — the YAML frontmatter block followed "
        f"by the article body. No preamble, no code fences, nothing else."
    )


def strip_fences(text):
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n", "", t)
        t = re.sub(r"\n```\s*$", "", t)
    return t.strip()


def generate_via_api(system_prompt, user_prompt):
    try:
        import anthropic
    except ImportError:
        sys.exit("Missing dep. Run:  pip install anthropic")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set.")
    client = anthropic.Anthropic()

    messages = [{"role": "user", "content": user_prompt}]
    text_out = ""
    # Loop to handle pause_turn (long agentic search sessions).
    for _ in range(6):
        resp = client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS,
            system=system_prompt, messages=messages, tools=[WEB_SEARCH],
        )
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                text_out += block.text
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        break
    return text_out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", help="ad-hoc title (skips the queue)")
    ap.add_argument("--audience", choices=["b2b", "patient"], help="track for --topic")
    ap.add_argument("--dry-run", action="store_true", help="no API call; write a stub")
    args = ap.parse_args()

    remaining = None
    if args.topic:
        audience = args.audience or "b2b"
        title = args.topic
    else:
        audience, title, remaining = next_from_queue()

    POSTS_DIR.mkdir(exist_ok=True)
    today = dt.date.today().isoformat()

    if args.dry_run:
        slug = slugify(title)
        md = (f"---\ntitle: \"{title}\"\nslug: \"{slug}\"\naudience: {audience}\n"
              f"category: \"Insights\"\ndate: {today}\nread_time: \"4 min read\"\n"
              f"summary: \"[dry-run stub]\"\nauthor: \"HeartCoach\"\nreviewed_by: \"\"\n"
              f"sources: []\n---\n\n[Dry-run stub for '{title}'. Real run calls the API.]\n")
    else:
        system_prompt = AGENT.read_text(encoding="utf-8")
        md = strip_fences(generate_via_api(system_prompt, build_user_prompt(audience, title)))
        if not md.startswith("---"):
            sys.exit("Model output did not start with YAML frontmatter; aborting without writing.")

    # Derive slug from frontmatter if present, else from title.
    m = re.search(r'^slug:\s*"?([^"\n]+)"?', md, re.MULTILINE)
    slug = slugify(m.group(1)) if m else slugify(title)
    out = POSTS_DIR / f"{today}-{slug}.md"
    out.write_text(md, encoding="utf-8")

    if remaining is not None:
        pop_queue(remaining, f"{audience} | {title}")

    print(f"Wrote draft: {out.relative_to(ROOT)}")
    print("reviewed_by is blank -> held by the review gate. Review, fill reviewed_by, then build.")


if __name__ == "__main__":
    main()
