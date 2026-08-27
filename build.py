#!/usr/bin/env python3
"""
HeartCoach Insights — static blog builder.

Reads posts/*.md (YAML frontmatter + Markdown body), renders each into a
self-contained, brand-styled HTML page, and regenerates the blog index.
Also emits insights-cards.html — the 3 latest cards to paste into the
homepage Insights section.

The clinical review gate: a post with `reviewed_by:` blank is a DRAFT. Drafts
are skipped by default. Pass --include-drafts to render them (watermarked) for
preview only — never deploy drafts.

Usage:
    pip install markdown pyyaml
    python build.py                 # build published posts -> site/
    python build.py --include-drafts

Dependencies: markdown, pyyaml (both pip-installable, no system packages).
"""

import argparse
import datetime as dt
import html
import pathlib
import re
import sys

try:
    import markdown
    import yaml
except ImportError:
    sys.exit("Missing deps. Run:  pip install markdown pyyaml")

ROOT = pathlib.Path(__file__).parent
POSTS_DIR = ROOT / "posts"
SITE_DIR = ROOT / "blog"

# ------------------------------------------------------------------ brand CSS
# Locked HeartCoach design system. Slate = trust, Sage = calm/data,
# Rose = care/attention. NEVER pure red. 18px body, 1.7 leading, 55+ friendly.
BRAND_CSS = """
:root{
  --slate-deep:#1C2B2A;--slate:#2D4A47;--slate-hover:#233B39;--sage-mid:#4A7A74;
  --sage-light:#A8C8C4;--sage-mist:#E8F2F1;--rose:#C97A7A;--rose-hover:#BB6A6A;
  --rose-light:#E8B0B0;--rose-mist:#FAF0F0;--bg:#F6F6F8;--surface:#FFFFFF;
  --text:#1C2B2A;--text-muted:#4A7A74;--on-dark-mut:rgba(255,255,255,.55);
  --font-head:"DM Sans",system-ui,-apple-system,sans-serif;
  --font-body:"Lato",system-ui,-apple-system,sans-serif;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:var(--font-body);font-size:18px;line-height:1.7;color:var(--text);background:var(--bg);-webkit-font-smoothing:antialiased}
h1,h2,h3,h4,.eyebrow{font-family:var(--font-head)}
h1,h2,h3,h4{font-weight:500;line-height:1.25;letter-spacing:-.01em;color:var(--slate-deep)}
em{font-style:italic;color:var(--rose)}
a{color:var(--slate)}
a:focus-visible,button:focus-visible{outline:2px solid var(--slate);outline-offset:2px;border-radius:6px}
.wrap{max-width:1140px;margin:0 auto;padding:0 28px}
/* nav */
header.nav{position:sticky;top:0;z-index:100;background:var(--slate-deep)}
.nav-inner{display:flex;align-items:center;justify-content:space-between;height:72px}
.logo{display:inline-flex;align-items:baseline;font-family:var(--font-head);font-size:1.4rem;font-weight:600}
.logo .mark{color:var(--rose-light);margin-right:8px;font-size:1.15rem}
.logo .heart-txt{color:#fff}.logo .coach-txt{color:var(--rose-light)}
.nav-links{display:flex;gap:6px}
.nav-links a{display:inline-flex;align-items:center;min-height:44px;padding:0 14px;font-family:var(--font-head);font-weight:500;font-size:1rem;color:var(--on-dark-mut);border-radius:8px}
.nav-links a:hover{color:#fff}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:52px;padding:14px 28px;font-family:var(--font-head);font-size:1.0625rem;font-weight:500;border-radius:999px;border:2px solid transparent;cursor:pointer;transition:background .18s,transform .18s}
.btn-care{background:var(--rose);color:#fff}.btn-care:hover{background:var(--rose-hover);transform:translateY(-1px)}
.btn-ghost{background:transparent;color:var(--slate);border-color:var(--sage-light)}
.btn-ghost:hover{background:var(--sage-mist);border-color:var(--sage-mid)}
/* article */
.article-hero{background:linear-gradient(180deg,var(--sage-mist),var(--bg));padding:64px 0 40px}
.article-hero .cat{font-family:var(--font-head);font-weight:600;font-size:.8rem;letter-spacing:.1em;text-transform:uppercase;color:var(--sage-mid)}
.article-hero h1{font-size:clamp(2rem,4.5vw,3rem);max-width:22ch;margin:16px 0 18px}
.article-hero .meta{color:var(--text-muted);font-size:1.02rem}
.article{max-width:720px;margin:0 auto;padding:48px 28px 24px}
.article p{margin:0 0 22px}
.article h2{font-size:1.6rem;margin:40px 0 14px}
.article h3{font-size:1.28rem;margin:30px 0 10px}
.article ul,.article ol{margin:0 0 22px 24px}
.article li{margin:0 0 10px}
.article a{color:var(--slate);text-decoration:underline;text-underline-offset:2px}
.article a:hover{color:var(--rose)}
.article blockquote{margin:26px 0;padding:16px 22px;background:var(--sage-mist);border-left:4px solid var(--rose);border-radius:0 12px 12px 0;font-size:1.15rem;color:var(--slate-deep)}
.article strong{color:var(--slate-deep)}
/* sources + footer blocks */
.sources{max-width:720px;margin:8px auto 0;padding:24px 28px;border-top:1px solid var(--sage-light)}
.sources h4{font-size:.85rem;letter-spacing:.08em;text-transform:uppercase;color:var(--sage-mid);margin-bottom:12px}
.sources ol{margin:0 0 0 20px}.sources li{margin-bottom:8px;font-size:.98rem;color:var(--text-muted)}
.sources a{color:var(--slate)}
.med-note{max-width:720px;margin:24px auto 0;padding:18px 22px;background:var(--rose-mist);border-left:4px solid var(--rose-light);border-radius:0 12px 12px 0;font-size:1rem;color:var(--slate-deep)}
.reviewed{max-width:720px;margin:16px auto 0;padding:0 28px;font-size:.92rem;color:var(--sage-mid)}
.post-cta{background:var(--slate-deep);color:#fff;text-align:center;padding:64px 0;margin-top:56px}
.post-cta h2{color:#fff;margin-bottom:14px}.post-cta em{color:var(--rose-light)}
.post-cta p{color:var(--on-dark-mut);max-width:520px;margin:0 auto 26px}
/* index */
.index-hero{background:linear-gradient(180deg,var(--sage-mist),var(--bg));padding:72px 0 40px;text-align:center}
.index-hero h1{font-size:clamp(2.2rem,5vw,3.2rem)}
.index-hero p{color:var(--text-muted);font-size:1.2rem;max-width:600px;margin:14px auto 0}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;padding:56px 0 80px}
.card{display:flex;flex-direction:column;background:var(--surface);border:1px solid var(--sage-light);border-radius:18px;overflow:hidden;box-shadow:0 1px 2px rgba(28,43,42,.04),0 4px 16px rgba(28,43,42,.05);transition:transform .18s,box-shadow .18s}
.card:hover{transform:translateY(-3px);box-shadow:0 8px 30px rgba(28,43,42,.09)}
.card .thumb{height:8px;background:linear-gradient(90deg,var(--sage-mid),var(--rose-light))}
.card .body{padding:26px;display:flex;flex-direction:column;flex:1}
.card .cat{font-family:var(--font-head);font-weight:600;font-size:.76rem;letter-spacing:.08em;text-transform:uppercase;color:var(--sage-mid)}
.card h3{font-size:1.2rem;margin:12px 0 10px}
.card h3 a{color:var(--slate-deep);text-decoration:none}.card h3 a:hover{color:var(--rose)}
.card p{color:var(--text-muted);font-size:1rem;flex:1}
.card .meta{margin-top:18px;font-size:.9rem;color:var(--sage-mid)}
.draft-flag{position:fixed;top:0;left:0;right:0;background:var(--rose);color:#fff;text-align:center;font-family:var(--font-head);font-weight:600;padding:8px;z-index:200;letter-spacing:.04em}
footer.foot{background:var(--slate-deep);padding:40px 0;border-top:1px solid rgba(255,255,255,.08)}
.foot-inner{display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap}
.foot-copy{color:rgba(255,255,255,.4);font-size:.95rem}
.back{display:inline-block;margin-top:8px;font-family:var(--font-head);font-weight:500;color:var(--slate)}
@media(max-width:940px){.grid{grid-template-columns:1fr}}
@media(max-width:760px){.nav-links{display:none}}
@media(prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700'
         '&family=Lato:wght@300;400;700&display=swap" rel="stylesheet">')

NAV = ('<header class="nav"><div class="wrap nav-inner">'
       '<a href="../index.html" class="logo" aria-label="HeartCoach home">'
       '<span class="mark" aria-hidden="true">&#9829;</span>'
       '<span class="heart-txt">Heart</span><span class="coach-txt">Coach</span></a>'
       '<nav class="nav-links" aria-label="Primary">'
       '<a href="../index.html#how">How It Works</a>'
       '<a href="../index.html#features">Features</a>'
       '<a href="index.html">Insights</a>'
       '<a href="../index.html#contact">Get Early Access</a></nav>'
       '</div></header>')

FOOTER = ('<footer class="foot"><div class="wrap foot-inner">'
          '<a href="../index.html" class="logo"><span class="mark" aria-hidden="true">&#9829;</span>'
          '<span class="heart-txt">Heart</span><span class="coach-txt">Coach</span></a>'
          '<div class="foot-copy">&copy; %d HeartCoach Inc. All rights reserved.</div>'
          '</div></footer>' % dt.date.today().year)

MED_NOTE = ("This article is general education, not medical advice. Always talk to "
            "your cardiologist or care team about your own situation. If you have "
            "symptoms like chest pain, severe shortness of breath, or fainting, "
            "call 911.")


def parse_post(path):
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.DOTALL)
    if not m:
        raise ValueError(f"{path.name}: missing YAML frontmatter")
    meta = yaml.safe_load(m.group(1)) or {}
    body_md = m.group(2)
    meta.setdefault("slug", path.stem)
    meta.setdefault("author", "HeartCoach")
    meta.setdefault("category", "Insights")
    meta.setdefault("read_time", "")
    meta.setdefault("reviewed_by", "")
    meta.setdefault("sources", [])
    meta["_body_html"] = markdown.markdown(body_md, extensions=["extra", "sane_lists"])
    meta["_is_patient"] = str(meta.get("audience", "")).lower() == "patient"
    meta["_published"] = bool(str(meta.get("reviewed_by", "")).strip())
    d = meta.get("date")
    meta["_date"] = d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d))
    meta["_date_disp"] = meta["_date"].strftime("%B %-d, %Y")
    return meta


def render_post(meta, draft=False):
    title = html.escape(str(meta["title"]))
    cat = html.escape(str(meta["category"]))
    summary = html.escape(str(meta.get("summary", "")))
    src_items = "".join(
        f'<li><a href="{html.escape(str(s["url"]))}" target="_blank" rel="noopener">{html.escape(str(s["label"]))}</a></li>'
        for s in meta.get("sources", []) if s.get("url")
    )
    sources_block = f'<div class="sources"><h4>Sources</h4><ol>{src_items}</ol></div>' if src_items else ""
    med_block = f'<div class="med-note">{MED_NOTE}</div>' if meta["_is_patient"] else ""
    reviewed_block = (f'<div class="reviewed">Clinically reviewed by {html.escape(str(meta["reviewed_by"]))}.</div>'
                      if meta["_is_patient"] and meta["reviewed_by"] else "")
    draft_banner = '<div class="draft-flag">DRAFT — not for publication. Pending review.</div>' if draft else ""
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — HeartCoach</title>
<meta name="description" content="{summary}">
{FONTS}<style>{BRAND_CSS}</style></head><body>{draft_banner}
{NAV}
<div class="article-hero"><div class="wrap"><div class="cat">{cat}</div>
<h1>{title}</h1><div class="meta">{meta["_date_disp"]} &middot; {html.escape(str(meta["read_time"]))}</div></div></div>
<article class="article">{meta["_body_html"]}</article>
{reviewed_block}{med_block}{sources_block}
<div class="wrap"><a class="back" href="index.html">&larr; All insights</a></div>
<section class="post-cta"><div class="wrap"><h2>Your heart has a <em>coach now.</em></h2>
<p>See how HeartCoach keeps cardiac patients engaged between every appointment.</p>
<a class="btn btn-care" href="../index.html#contact">Get early access</a></div></section>
{FOOTER}</body></html>"""


def render_index(posts):
    cards = ""
    for m in posts:
        cards += (f'<article class="card"><div class="thumb"></div><div class="body">'
                  f'<span class="cat">{html.escape(str(m["category"]))}</span>'
                  f'<h3><a href="{m["slug"]}.html">{html.escape(str(m["title"]))}</a></h3>'
                  f'<p>{html.escape(str(m.get("summary", "")))}</p>'
                  f'<div class="meta">{m["_date_disp"]} &middot; {html.escape(str(m["read_time"]))}</div>'
                  f'</div></article>')
    if not cards:
        cards = '<p style="color:var(--text-muted)">No published posts yet.</p>'
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Insights — HeartCoach</title>
<meta name="description" content="Evidence, behavioral science, and practical guidance on cardiac patient engagement.">
{FONTS}<style>{BRAND_CSS}</style></head><body>
{NAV}
<div class="index-hero"><div class="wrap"><h1>The latest from <em>HeartCoach</em></h1>
<p>Evidence, behavioral science, and practical guidance on keeping cardiac patients engaged between visits.</p></div></div>
<div class="wrap"><div class="grid">{cards}</div></div>
{FOOTER}</body></html>"""


def render_home_partial(posts):
    """3 latest cards to paste into the homepage Insights section."""
    out = ""
    for m in posts[:3]:
        out += (f'<article class="post"><div class="thumb" aria-hidden="true"></div><div class="body">'
                f'<span class="cat">{html.escape(str(m["category"]))}</span>'
                f'<h3><a href="blog/{m["slug"]}.html">{html.escape(str(m["title"]))}</a></h3>'
                f'<p>{html.escape(str(m.get("summary", "")))}</p>'
                f'<div class="meta">{m["_date_disp"]} &middot; {html.escape(str(m["read_time"]))}</div>'
                f'</div></article>\n')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-drafts", action="store_true",
                    help="also render unreviewed drafts (watermarked, preview only)")
    args = ap.parse_args()

    SITE_DIR.mkdir(exist_ok=True)
    all_posts = [parse_post(p) for p in sorted(POSTS_DIR.glob("*.md"))]
    all_posts.sort(key=lambda m: m["_date"], reverse=True)

    published = [m for m in all_posts if m["_published"]]
    drafts = [m for m in all_posts if not m["_published"]]

    rendered = 0
    for m in published:
        (SITE_DIR / f'{m["slug"]}.html').write_text(render_post(m), encoding="utf-8")
        rendered += 1
    if args.include_drafts:
        for m in drafts:
            (SITE_DIR / f'{m["slug"]}.html').write_text(render_post(m, draft=True), encoding="utf-8")

    (SITE_DIR / "index.html").write_text(render_index(published), encoding="utf-8")
    (SITE_DIR / "insights-cards.partial.html").write_text(render_home_partial(published), encoding="utf-8")

    print(f"Built {rendered} published post(s) -> {SITE_DIR}/")
    print(f"  index.html + insights-cards.partial.html regenerated.")
    if drafts:
        gate = "rendered (watermarked)" if args.include_drafts else "HELD (review gate)"
        print(f"  {len(drafts)} draft(s) {gate}:")
        for m in drafts:
            why = "patient post needs clinical sign-off" if m["_is_patient"] else "needs review"
            print(f"    - {m['slug']}  ({why}; set reviewed_by to publish)")


if __name__ == "__main__":
    main()
