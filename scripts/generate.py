"""Generate the animated SVG cards used by README.md.

Usage:
    python scripts/generate.py            # uses profile.json

Outputs (in ./assets):
    header-dark.svg / header-light.svg   name banner with a looping typing effect
    card-dark.svg   / card-light.svg     neofetch-style terminal card
Also refreshes the icon rows in README.md from profile.json "skills" and "languages"
(icons added by hand in README are kept).

No third-party dependencies.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

MONO = "'JetBrains Mono','Fira Code','Cascadia Code',Consolas,'DejaVu Sans Mono',monospace"
SANS = "'Segoe UI','Inter',system-ui,-apple-system,Helvetica,Arial,sans-serif"
NBSP = " "  # renderers never collapse it, so monospace columns stay aligned

THEMES = {
    "dark": {
        # plain, colourless dark pane (no background blobs)
        "glass": "#0d1117",
        "bar": "rgba(255,255,255,0.04)",
        "hair": "rgba(255,255,255,0.10)",
        "text": "#e6edf3",
        "dim": "#7d8590",
        "accent": "#a78bfa",
        "accent2": "#22d3ee",
        "accent3": "#34d399",
        "blobs": ["#7c3aed", "#06b6d4", "#db2777"],
        "blob_opacity": 0,
    },
    "light": {
        # frosted glass: a see-through pane over large saturated blobs, plus sheen and grain
        "glass": "rgba(255,255,255,0.40)",
        "bar": "rgba(255,255,255,0.35)",
        "hair": "rgba(31,35,40,0.14)",
        "text": "#1f2328",
        "dim": "#57606a",
        "accent": "#7c3aed",
        "accent2": "#0e7490",
        "accent3": "#047857",
        "blobs": ["#a78bfa", "#22d3ee", "#f472b6"],
        "blob_opacity": 0.85,
        "blob_scale": 1.6,
        "sheen": 0.6,
        "grain": 0.07,
    },
}


# --------------------------------------------------------------------------- helpers
def esc(s: str) -> str:
    return escape(s.replace(" ", NBSP), {'"': "&quot;"})


def fmt(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".")


def discrete(attr: str, events: list[tuple[float, float]], dur: float,
             begin: str = "0s", repeat: bool = False) -> str:
    """SMIL discrete animation from (time, value) events over a cycle of `dur` seconds."""
    events = sorted(events)
    if not events or events[0][0] > 0:
        events.insert(0, (0.0, events[0][1] if events else 0))
    times, values, last = [], [], -1.0
    for t, v in events:
        kt = round(min(max(t / dur, 0), 1), 4)
        if kt <= last:
            values[-1] = v  # same keyTime: keep latest value
            continue
        times.append(kt)
        values.append(v)
        last = kt
    rep = 'repeatCount="indefinite"' if repeat else 'fill="freeze"'
    return (f'<animate attributeName="{attr}" calcMode="discrete" dur="{fmt(dur)}s" begin="{begin}" '
            f'keyTimes="{";".join(fmt(t) if t else "0" for t in times)}" '
            f'values="{";".join(fmt(v) for v in values)}" {rep}/>')


def defs_common(p: dict, uid: str, w: int, h: int) -> str:
    b = p["blobs"]
    k = p.get("blob_scale", 1)
    extra = ""
    if p.get("sheen"):
        extra += f"""
    <linearGradient id="{uid}-sheen" x1="0" y1="0" x2="0.35" y2="1">
      <stop offset="0" stop-color="#fff" stop-opacity="{p['sheen']}"/>
      <stop offset="0.45" stop-color="#fff" stop-opacity="0.08"/>
      <stop offset="1" stop-color="#fff" stop-opacity="0"/>
    </linearGradient>"""
    if p.get("grain"):
        extra += f"""
    <filter id="{uid}-grain" x="0" y="0" width="100%" height="100%">
      <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch"/>
      <feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0"/>
    </filter>"""
    return f"""{extra}
    <linearGradient id="{uid}-border" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{w}" y2="{h}">
      <stop offset="0" stop-color="{p['accent']}"/>
      <stop offset="0.5" stop-color="{p['accent2']}"/>
      <stop offset="1" stop-color="{p['accent']}"/>
      <animateTransform attributeName="gradientTransform" type="rotate"
        values="0 {w/2} {h/2};360 {w/2} {h/2}" dur="10s" repeatCount="indefinite"/>
    </linearGradient>
    <linearGradient id="{uid}-text" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{p['accent']}"/>
      <stop offset="1" stop-color="{p['accent2']}"/>
    </linearGradient>
    <filter id="{uid}-blur" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="55"/>
    </filter>
    <filter id="{uid}-glow" x="-10%" y="-10%" width="120%" height="120%">
      <feGaussianBlur stdDeviation="6"/>
    </filter>
    <clipPath id="{uid}-win"><rect x="10" y="10" width="{w-20}" height="{h-20}" rx="16"/></clipPath>
    <g id="{uid}-blobs" filter="url(#{uid}-blur)" opacity="{p['blob_opacity']}">
      <circle cx="{w*0.15}" cy="{h*0.2}" r="{fmt(h*0.35*k)}" fill="{b[0]}">
        <animate attributeName="cx" values="{w*0.15};{w*0.35};{w*0.15}" dur="14s" repeatCount="indefinite"/>
      </circle>
      <circle cx="{w*0.85}" cy="{h*0.85}" r="{fmt(h*0.4*k)}" fill="{b[1]}">
        <animate attributeName="cy" values="{h*0.85};{h*0.3};{h*0.85}" dur="12s" repeatCount="indefinite"/>
      </circle>
      <circle cx="{w*0.55}" cy="{h*0.1}" r="{fmt(h*0.25*k)}" fill="{b[2]}">
        <animate attributeName="cx" values="{w*0.55};{w*0.7};{w*0.55}" dur="16s" repeatCount="indefinite"/>
      </circle>
    </g>"""


def glass_window(p: dict, uid: str, w: int, h: int) -> str:
    """Background blobs + frosted panel + animated gradient border with glow."""
    return f"""
  <g clip-path="url(#{uid}-win)">
    {f'<use href="#{uid}-blobs"/>' if p.get("blob_opacity") else ""}
    <rect x="10" y="10" width="{w-20}" height="{h-20}" fill="{p['glass']}"/>{f'''
    <rect x="10" y="10" width="{w-20}" height="{h-20}" filter="url(#{uid}-grain)" opacity="{p['grain']}"/>''' if p.get("grain") else ""}{f'''
    <rect x="10" y="10" width="{w-20}" height="{h-20}" fill="url(#{uid}-sheen)"/>''' if p.get("sheen") else ""}
  </g>
  <rect x="10" y="10" width="{w-20}" height="{h-20}" rx="16" fill="none"
        stroke="url(#{uid}-border)" stroke-width="3" opacity="0.6" filter="url(#{uid}-glow)"/>
  <rect x="10.75" y="10.75" width="{w-21.5}" height="{h-21.5}" rx="15.5" fill="none"
        stroke="url(#{uid}-border)" stroke-width="1.5"/>"""


# --------------------------------------------------------------------------- card
def build_card(cfg: dict, theme: str) -> str:
    p = THEMES[theme]
    uid = f"card{theme[0]}"
    W = 960
    fs, lh = 13, 20
    cw = fs * 0.6
    key_w = 100                      # gap between key and value columns
    cols = [44, W / 2 + 22]           # x of the two columns
    col_right = [W / 2 - 10, W - 34]  # right edge each column may use
    split = cfg.get("left_sections", 2)
    speed = 0.012

    out, clips = [], []
    state = {"t": 0.5, "n": 0}

    def typed(y0: float, parts: list[tuple[float, str, str, str]]) -> float:
        """parts: (x, text, fill, weight). Adds one clip-revealed (typed) line; returns end time."""
        state["n"] += 1
        cid = f"{uid}-l{state['n']}"
        x0 = parts[0][0]
        t0, total, events = state["t"], 0, [(0.0, 0)]
        for x, s, _, _ in parts:
            for i in range(1, len(s) + 1):
                total += 1
                events.append((t0 + total * speed, (x - x0) + i * cw))
        end = t0 + total * speed
        events.append((end + 0.001, W))
        clips.append(f'<clipPath id="{cid}"><rect x="{fmt(x0 - 2)}" y="{fmt(y0 - fs)}" width="0" height="{lh}">'
                     f'{discrete("width", events, end + 0.01)}</rect></clipPath>')
        body = "".join(
            f'<text x="{fmt(x)}" y="{fmt(y0)}" fill="{fill}" font-weight="{wt}" '
            f'textLength="{fmt(len(s) * cw)}" lengthAdjust="spacing">{esc(s)}</text>'
            for x, s, fill, wt in parts if s)
        out.append(f'<g clip-path="url(#{cid})">{body}</g>')
        state["t"] = end + 0.06
        return end

    def section_block(x: float, y: float, secs: list[dict], right: float):
        max_chars = int((right - x - key_w) / cw)
        last = (state["t"], x, y)
        for si, sec in enumerate(secs):
            if si:
                y += 10
            if sec.get("title"):
                typed(y, [(x, "~ ", p["accent3"], "700"), (x + 2 * cw, sec["title"], p["accent"], "700")])
                y += lh
            for key, val in sec["items"]:
                if len(val) > max_chars:
                    val = val[: max_chars - 1] + "…"
                if key is None:
                    parts = [(x, val, p["dim"], "400")]
                    end_x = x + len(val) * cw
                else:
                    parts = [(x, key, p["accent2"], "700"), (x + key_w, val, p["text"], "400")]
                    end_x = x + key_w + len(val) * cw
                last = (typed(y, parts), end_x, y)
                y += lh
        return y, last

    # left column: user@host header + first sections
    top = 88
    host = f"{cfg['username']}@github"
    typed(top, [(cols[0], host, p["accent"], "700")])
    out.append(f'<rect x="{cols[0]}" y="{top + 9}" width="{fmt(len(host) * cw)}" height="2" rx="1" '
               f'fill="url(#{uid}-text)"/>')
    y_left, _ = section_block(cols[0], top + 34, cfg["sections"][:split], col_right[0])

    # right column: remaining sections, aligned with the left column's first row
    y_right, (last_end, last_x, last_y) = section_block(cols[1], top, cfg["sections"][split:], col_right[1])

    H = int(max(y_left, y_right) + 18)
    divider = (f'<line x1="{W / 2}" y1="{top - 14}" x2="{W / 2}" y2="{H - 34}" '
               f'stroke="{p["hair"]}" stroke-dasharray="3 5"/>')
    cursor = (f'<rect x="{fmt(last_x + 4)}" y="{fmt(last_y - fs + 2)}" width="{fmt(cw)}" height="{fs + 1}" '
              f'fill="{p["accent3"]}" opacity="0"><animate attributeName="opacity" values="1;0" calcMode="discrete" '
              f'dur="1s" begin="{fmt(last_end + 0.1)}s" repeatCount="indefinite"/></rect>')

    title = f"{cfg['username']}@github: ~/README.md"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(cfg['name'])} - profile card">
  <title>{esc(cfg['name'])}</title>
  <defs>{defs_common(p, uid, W, H)}
    {"".join(clips)}
  </defs>
{glass_window(p, uid, W, H)}
  <!-- title bar -->
  <rect x="11" y="11" width="{W - 22}" height="40" rx="15" fill="{p['bar']}"/>
  <line x1="11" y1="51" x2="{W - 11}" y2="51" stroke="{p['hair']}"/>
  <circle cx="34" cy="31" r="6" fill="#ff5f57"/><circle cx="54" cy="31" r="6" fill="#febc2e"/><circle cx="74" cy="31" r="6" fill="#28c840"/>
  <text x="{W / 2}" y="35" text-anchor="middle" font-family="{MONO}" font-size="12" fill="{p['dim']}">{esc(title)}</text>
  {divider}

  <!-- neofetch info -->
  <g font-family="{MONO}" font-size="{fs}">
    {"".join(out)}
    {cursor}
  </g>
</svg>
"""


# --------------------------------------------------------------------------- header
def build_header(cfg: dict, theme: str) -> str:
    p = THEMES[theme]
    uid = f"head{theme[0]}"
    W, H = 960, 210
    fs, cw = 20, 12.0
    tx = 70
    ty = 138

    # looping typing / deleting cycle across all roles
    plan, t = [], 0.4
    for role in cfg["roles"]:
        n = len(role)
        start = t
        typed_end = start + n * 0.065
        hold_end = typed_end + 1.8
        del_end = hold_end + n * 0.028
        plan.append((role, start, typed_end, hold_end, del_end))
        t = del_end + 0.35
    cycle = t

    roles_svg, clips, cursor_ev = [], [], [(0.0, tx)]
    for i, (role, s, te, he, de) in enumerate(plan):
        n = len(role)
        ev = [(0.0, 0)]
        for k in range(1, n + 1):
            ev.append((s + k * (te - s) / n, k * cw))
            cursor_ev.append((s + k * (te - s) / n, tx + k * cw))
        for k in range(1, n + 1):
            ev.append((he + k * (de - he) / n, (n - k) * cw))
            cursor_ev.append((he + k * (de - he) / n, tx + (n - k) * cw))
        cid = f"{uid}-r{i}"
        clips.append(f'<clipPath id="{cid}"><rect x="{tx}" y="{ty - fs}" width="0" height="{fs + 8}">'
                     f'{discrete("width", ev, cycle, repeat=True)}</rect></clipPath>')
        roles_svg.append(f'<text x="{tx}" y="{ty}" clip-path="url(#{cid})" textLength="{fmt(n * cw)}" '
                         f'lengthAdjust="spacing">{esc(role)}</text>')

    cursor = (f'<rect x="{tx}" y="{ty - fs + 3}" width="3" height="{fs + 2}" rx="1" fill="{p["accent3"]}">'
              f'{discrete("x", cursor_ev, cycle, repeat=True)}'
              f'<animate attributeName="opacity" values="1;0" calcMode="discrete" dur="0.9s" repeatCount="indefinite"/></rect>')

    name = escape(cfg["name"])
    greeting = escape(cfg.get("greeting", "Hi, I'm"))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{greeting} {name}">
  <title>{greeting} {name}</title>
  <defs>{defs_common(p, uid, W, H)}
    {"".join(clips)}
  </defs>
{glass_window(p, uid, W, H)}
  <text x="44" y="82" font-family="{SANS}" font-size="40" font-weight="800" fill="{p['text']}">{greeting} <tspan fill="url(#{uid}-text)">{name}</tspan></text>
  <g transform="translate({W - 80} 70)">
    <text x="0" y="0" font-size="40" text-anchor="middle" dominant-baseline="central">👋
      <animateTransform attributeName="transform" type="rotate" values="0;18;-8;18;0;0" keyTimes="0;0.1;0.2;0.3;0.4;1" dur="2.5s" repeatCount="indefinite"/>
    </text>
  </g>
  <text x="44" y="{ty}" font-family="{MONO}" font-size="{fs}" font-weight="700" fill="{p['accent3']}">❯</text>
  <g font-family="{MONO}" font-size="{fs}" fill="{p['accent2']}">
    {"".join(roles_svg)}
  </g>
  {cursor}
  <text x="44" y="178" font-family="{MONO}" font-size="13" fill="{p['dim']}">// {escape(cfg.get('tagline', ''))}</text>
</svg>
"""


# --------------------------------------------------------------------------- README icon rows
# Each block lives between "<!-- NAME:start ... -->" and "<!-- NAME:end -->" in README.md.
ICON_BLOCKS = [  # (marker name, profile.json key, alt text)
    ("skills", "skills", "Teknolojiler"),
    ("languages", "languages", "Diller"),
]
PICTURE_RE = re.compile(r"<picture>.*?</picture>\n?", re.S)
ICON_IDS_RE = re.compile(r"skillicons\.dev/icons\?i=([^&\"'\s]+)")


def _norm(ids: list[str]) -> list[str]:
    return [s.strip().lower() for s in ids if s.strip()]


def merge_ids(base: list[str], extra: list[str]) -> list[str]:
    """Union of both lists. Base order wins; ids only in `extra` go right after their neighbour there."""
    merged = list(dict.fromkeys(base))
    prev = None
    for sid in extra:
        if sid not in merged:
            pos = merged.index(prev) + 1 if prev in merged else (len(merged) if prev else 0)
            merged.insert(pos, sid)
        prev = sid
    return merged


def update_icon_block(text: str, name: str, config_ids: list[str], alt: str) -> str:
    """Rewrite the <picture> between the NAME markers.

    Icons from profile.json and icons written by hand into that block's icon URLs are merged,
    so nothing added in either place is lost. Everything else inside the markers stays as is.
    Icon ids come from https://skillicons.dev (e.g. python, cpp, docker, windows).
    """
    start, end = text.find(f"<!-- {name}:start"), text.find(f"<!-- {name}:end -->")
    if start == -1 or end == -1 or end < start:
        print(f"README.md has no {name} markers; skipping")
        return text
    body_start = text.index("\n", start) + 1
    body = text[body_start:end]

    picture = PICTURE_RE.search(body)
    ids = _norm(config_ids)
    if picture:
        for group in ICON_IDS_RE.findall(picture.group(0)):
            ids = merge_ids(ids, _norm(re.split(r"%2C|,", group, flags=re.I)))

    block = ""
    if ids:
        url = f"https://skillicons.dev/icons?i={'%2C'.join(ids)}&perline=14&theme="  # encoded commas: srcset splits on ","
        block = (f'<picture>\n'
                 f'  <source media="(prefers-color-scheme: dark)" srcset="{url}dark">\n'
                 f'  <source media="(prefers-color-scheme: light)" srcset="{url}light">\n'
                 f'  <img alt="{alt}" src="{url}dark">\n'
                 f'</picture>\n')
    new_body = (body[:picture.start()] + block + body[picture.end():]) if picture else block + body
    return text[:body_start] + new_body + text[end:]


def update_readme_icons(cfg: dict) -> bool:
    """Refresh every icon row in README.md. Returns True when the file changed."""
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    new = text
    for name, key, alt in ICON_BLOCKS:
        new = update_icon_block(new, name, cfg.get(key, []), alt)
    if new != text:
        readme.write_text(new, encoding="utf-8")
    return new != text


def build_divider(label: str, theme: str) -> str:
    """Small gradient line with a label in the middle: ──── diller ────"""
    p = THEMES[theme]
    uid = f"div{theme[0]}"
    w, h = 320, 30
    tw = len(label) * 7.2 + 24
    l_end, r_start = (w - tw) / 2, (w + tw) / 2
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(label)}">
  <defs>
    <linearGradient id="{uid}-l" x1="0" x2="1"><stop offset="0" stop-color="{p['accent']}" stop-opacity="0"/><stop offset="1" stop-color="{p['accent']}"/></linearGradient>
    <linearGradient id="{uid}-r" x1="0" x2="1"><stop offset="0" stop-color="{p['accent2']}"/><stop offset="1" stop-color="{p['accent2']}" stop-opacity="0"/></linearGradient>
  </defs>
  <rect x="0" y="{h / 2 - 1}" width="{fmt(l_end)}" height="2" rx="1" fill="url(#{uid}-l)"/>
  <rect x="{fmt(r_start)}" y="{h / 2 - 1}" width="{fmt(w - r_start)}" height="2" rx="1" fill="url(#{uid}-r)"/>
  <text x="{w / 2}" y="{h / 2 + 4}" text-anchor="middle" font-family="{MONO}" font-size="12" fill="{p['dim']}">{esc(label)}</text>
</svg>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "profile.json"))
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    ASSETS.mkdir(exist_ok=True)
    for theme in THEMES:
        (ASSETS / f"card-{theme}.svg").write_text(build_card(cfg, theme), encoding="utf-8")
        (ASSETS / f"header-{theme}.svg").write_text(build_header(cfg, theme), encoding="utf-8")
        (ASSETS / f"divider-{theme}.svg").write_text(build_divider("diller", theme), encoding="utf-8")
    print("Wrote: card-*.svg, header-*.svg, divider-*.svg")
    if update_readme_icons(cfg):
        print("Updated README.md icon rows")


if __name__ == "__main__":
    main()
