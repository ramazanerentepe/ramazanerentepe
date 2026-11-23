"""Generate the GitHub stats cards.

    assets/stats-{en,tr}-{dark,light}.svg     stats list + "languages by repo" donut
    assets/activity-{en,tr}-{dark,light}.svg  profile summary + last-year contributions chart

Usage:
    python scripts/stats.py                    # live data, needs $GITHUB_TOKEN (GraphQL)
    python scripts/stats.py --data stats.json  # render from a saved JSON file
    python scripts/stats.py --dump stats.json  # fetch and also save the JSON

Runs weekly in .github/workflows/stats.yml. No third-party dependencies.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from generate import ASSETS, LANGS, MONO, ROOT, SANS, THEMES, defs_common, esc, fmt, for_lang, glass_window

API = "https://api.github.com"
W = 960

LANG_COLORS = {
    "Python": "#3572A5", "Java": "#b07219", "C++": "#f34b7d", "C": "#8b949e",
    "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "HTML": "#e34c26", "CSS": "#663399",
    "Shell": "#89e051", "C#": "#178600", "Go": "#00ADD8", "Rust": "#dea584",
    "Kotlin": "#A97BFF", "Dart": "#00B4AB", "PHP": "#4F5D95", "Jupyter Notebook": "#DA5B0B",
}

# card texts per language (cfg["lang"] picks one)
TEXT = {
    "en": {
        "stars": "Total Stars", "commits": "Total Commits", "prs": "Total PRs", "issues": "Total Issues",
        "contributed": "Contributed to", "stats_title": "GitHub Stats", "langs_title": "Top Languages by Repo",
        "other": "Other", "no_langs": "No language data yet", "stats_label": "GitHub stats",
        "year_total": "{n} contributions in the last year", "public_repos": "{n} public repos",
        "joined": "Joined GitHub {n} years ago", "joined_one": "Joined GitHub 1 year ago",
        "joined_new": "Joined GitHub this year", "chart_label": "contributions in the last year",
        "activity_label": "GitHub contributions chart", "repo_one": "repo", "repo_many": "repos",
    },
    "tr": {
        "stars": "Toplam Yıldız", "commits": "Toplam Commit", "prs": "Toplam PR", "issues": "Toplam Issue",
        "contributed": "Katkı Verilen Repo", "stats_title": "GitHub İstatistikleri", "langs_title": "Repo Bazında Diller",
        "other": "Diğer", "no_langs": "Henüz dil verisi yok", "stats_label": "GitHub istatistikleri",
        "year_total": "Son 1 yılda {n} katkı", "public_repos": "{n} açık repo",
        "joined": "GitHub'a {n} yıl önce katıldı", "joined_one": "GitHub'a 1 yıl önce katıldı",
        "joined_new": "GitHub'a bu yıl katıldı", "chart_label": "son 1 yılın katkıları",
        "activity_label": "GitHub katkı grafiği", "repo_one": "repo", "repo_many": "repo",
    },
}


QUERY = """
query($login: String!) {
  user(login: $login) {
    name login createdAt
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100, privacy: PUBLIC) {
      totalCount
      nodes { name stargazerCount primaryLanguage { name color } }
    }
    pullRequests { totalCount }
    issues { totalCount }
    repositoriesContributedTo(includeUserRepositories: true,
                              contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]) { totalCount }
    contributionsCollection {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
  }
}"""


# --------------------------------------------------------------------------- data
def _request(path: str, token: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode() if body else None,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "profile-readme-stats",
                 "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch(login: str, token: str) -> dict:
    res = _request("/graphql", token, {"query": QUERY, "variables": {"login": login}})
    if res.get("errors"):
        raise SystemExit(f"GraphQL error: {res['errors']}")
    u = res["data"]["user"]
    repos = [r for r in u["repositories"]["nodes"] if r["name"].lower() != login.lower()]
    langs: dict[str, int] = {}
    colors: dict[str, str] = {}
    for r in repos:
        if r["primaryLanguage"]:
            name = r["primaryLanguage"]["name"]
            langs[name] = langs.get(name, 0) + 1
            colors[name] = r["primaryLanguage"]["color"]
    days = [[d["date"], d["contributionCount"]]
            for w in u["contributionsCollection"]["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    commits = _request(f"/search/commits?q=author:{login}&per_page=1", token)["total_count"]
    return {
        "name": u["name"] or login, "login": u["login"], "created_at": u["createdAt"],
        "stars": sum(r["stargazerCount"] for r in repos), "commits": commits,
        "prs": u["pullRequests"]["totalCount"], "issues": u["issues"]["totalCount"],
        "contributed_to": u["repositoriesContributedTo"]["totalCount"],
        "public_repos": u["repositories"]["totalCount"],
        "repo_languages": langs, "lang_colors": colors, "calendar": days,
    }


# --------------------------------------------------------------------------- icons (16x16)
def icon(kind: str, x: float, y: float, color: str) -> str:
    s = {
        "star": '<path d="M8 1.5l1.9 4 4.4.5-3.3 3 .9 4.3L8 11.1l-3.9 2.2.9-4.3-3.3-3 4.4-.5z"/>',
        "commit": '<circle cx="8" cy="8" r="3"/><path d="M0.5 8H5M11 8h4.5"/>',
        "pr": '<circle cx="4" cy="3.5" r="2"/><circle cx="4" cy="12.5" r="2"/><circle cx="12" cy="12.5" r="2"/>'
              '<path d="M4 5.5v5M12 10.5V6.5a2.5 2.5 0 0 0-2.5-2.5H7.5M9 2.5L7.5 4 9 5.5"/>',
        "issue": '<circle cx="8" cy="8" r="6.5"/><circle cx="8" cy="8" r="1.2" fill="currentColor"/>',
        "repo": '<path d="M3 13.5V3a1.5 1.5 0 0 1 1.5-1.5H13.5V12H4.5A1.5 1.5 0 0 0 3 13.5a1.5 1.5 0 0 0 1.5 1.5H13.5"/>',
        "pulse": '<path d="M0.5 8.5h3l2-5 3 9 2-6 1.5 2h3.5"/>',
        "clock": '<circle cx="8" cy="8" r="6.5"/><path d="M8 4.5V8l2.5 1.5"/>',
        "school": '<path d="M1 6l7-3.5L15 6 8 9.5z"/><path d="M4 7.5v4c2.5 1.8 5.5 1.8 8 0v-4"/>',
    }[kind]
    return (f'<g transform="translate({fmt(x)} {fmt(y)})" fill="none" stroke="{color}" stroke-width="1.5" '
            f'stroke-linecap="round" stroke-linejoin="round" color="{color}">{s}</g>')


def title_bar(p: dict, title: str) -> str:
    return f"""
  <rect x="11" y="11" width="{W - 22}" height="40" rx="15" fill="{p['bar']}"/>
  <line x1="11" y1="51" x2="{W - 11}" y2="51" stroke="{p['hair']}"/>
  <circle cx="34" cy="31" r="6" fill="#ff5f57"/><circle cx="54" cy="31" r="6" fill="#febc2e"/><circle cx="74" cy="31" r="6" fill="#28c840"/>
  <text x="{W / 2}" y="35" text-anchor="middle" font-family="{MONO}" font-size="12" fill="{p['dim']}">{esc(title)}</text>"""


def fade(i: float, base: float = 0.3) -> str:
    return (f'opacity="0"><animate attributeName="opacity" from="0" to="1" begin="{fmt(base + i * 0.12)}s" '
            f'dur="0.4s" fill="freeze"/>')


def heading(p: dict, x: float, y: float, text: str) -> str:
    return (f'<text x="{fmt(x)}" y="{y}" fill="{p["accent3"]}" font-weight="700">~ '
            f'<tspan fill="{p["accent"]}">{esc(text)}</tspan></text>')


# --------------------------------------------------------------------------- card 1: stats + donut
def build_stats(cfg: dict, d: dict, theme: str) -> str:
    p = THEMES[theme]
    t = TEXT[cfg.get("lang", "tr")]
    uid = f"stats{theme[0]}"
    H, top, lh = 296, 92, 32
    lx, rx = 44, W / 2 + 32

    rows = [("star", t["stars"], d["stars"]), ("commit", t["commits"], d["commits"]),
            ("pr", t["prs"], d["prs"]), ("issue", t["issues"], d["issues"]),
            ("repo", t["contributed"], d["contributed_to"])]
    left = [heading(p, lx, top, t["stats_title"])]
    for i, (ic, label, value) in enumerate(rows):
        y = top + 40 + i * lh
        left.append(f'<g {fade(i)}{icon(ic, lx, y - 12, p["accent"])}'
                    f'<text x="{lx + 28}" y="{y}" fill="{p["accent2"]}" font-weight="700">{esc(label)}</text>'
                    f'<text x="{lx + 250}" y="{y}" fill="{p["text"]}" font-weight="700">{value}</text></g>')

    hidden = set(cfg.get("hide_languages", []))
    langs = sorted(((k, v) for k, v in d["repo_languages"].items() if k not in hidden), key=lambda kv: (-kv[1], kv[0]))
    shown = langs[:5]
    if len(langs) > 5:
        shown.append((t["other"], sum(v for _, v in langs[5:])))
    total = sum(v for _, v in shown) or 1
    colors = {**LANG_COLORS, **d.get("lang_colors", {})}

    right = [heading(p, rx, top, t["langs_title"])]
    cx, cy, r, sw = W - 34 - 105, 168, 64, 22
    circ = 2 * math.pi * r
    arcs, acc = [], 0.0
    gap = 2.5 if len(shown) > 1 else 0
    for i, (name, n) in enumerate(shown):
        color = colors.get(name) or p["dim"]
        seg = circ * n / total
        dash = max(seg - gap, 0.1)
        arcs.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{sw}" '
                    f'stroke-dasharray="0 {fmt(circ)}" stroke-dashoffset="{fmt(-acc)}" transform="rotate(-90 {cx} {cy})">'
                    f'<animate attributeName="stroke-dasharray" from="0 {fmt(circ)}" to="{fmt(dash)} {fmt(circ)}" '
                    f'begin="{fmt(0.4 + i * 0.18)}s" dur="0.6s" fill="freeze"/></circle>')
        acc += seg
        y = top + 40 + i * 30
        right.append(f'<g {fade(i + 1)}<rect x="{fmt(rx)}" y="{y - 12}" width="14" height="14" rx="3" fill="{color}"/>'
                     f'<text x="{fmt(rx + 24)}" y="{y}" fill="{p["text"]}">{esc(name)}</text>'
                     f'<text x="{fmt(rx + 190)}" y="{y}" fill="{p["dim"]}" text-anchor="end">{n} {t["repo_one"] if n == 1 else t["repo_many"]}</text></g>')
    if not shown:
        right.append(f'<text x="{fmt(rx)}" y="{top + 40}" fill="{p["dim"]}">{t["no_langs"]}</text>')
    donut = (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{p["hair"]}" stroke-width="{sw}"/>'
             + "".join(arcs)
             + f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" fill="{p["text"]}" font-size="22" font-weight="800">{sum(v for _, v in langs)}</text>'
             f'<text x="{cx}" y="{cy + 16}" text-anchor="middle" fill="{p["dim"]}" font-size="11">{t["repo_many"]}</text>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{t['stats_label']}">
  <title>{t['stats_label']}</title>
  <defs>{defs_common(p, uid, W, H)}</defs>
{glass_window(p, uid, W, H)}{title_bar(p, f"{cfg['username']}@github: ~/stats")}
  <line x1="{W / 2}" y1="{top - 14}" x2="{W / 2}" y2="{H - 30}" stroke="{p['hair']}" stroke-dasharray="3 5"/>
  <g font-family="{MONO}" font-size="13">
    {"".join(left)}
    {"".join(right)}
    {donut}
  </g>
</svg>
"""


# --------------------------------------------------------------------------- card 2: activity chart
def smooth_path(pts: list[tuple[float, float]], floor_y: float) -> str:
    """Catmull-Rom spline through pts as cubic beziers (control points clamped above floor_y)."""
    d = f"M{fmt(pts[0][0])} {fmt(pts[0][1])}"
    for i in range(len(pts) - 1):
        p0, p1, p2 = pts[max(i - 1, 0)], pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, min(p1[1] + (p2[1] - p0[1]) / 6, floor_y))
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, min(p2[1] - (p3[1] - p1[1]) / 6, floor_y))
        d += f" C{fmt(c1[0])} {fmt(c1[1])} {fmt(c2[0])} {fmt(c2[1])} {fmt(p2[0])} {fmt(p2[1])}"
    return d


def nice_max(v: int) -> tuple[int, int]:
    """Axis max and step giving 4-5 ticks."""
    v = max(v, 4)
    for step in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
        if v / step <= 5:
            return math.ceil(v / step) * step, step
    return v, v // 4


def build_activity(cfg: dict, d: dict, theme: str) -> str:
    p = THEMES[theme]
    t = TEXT[cfg.get("lang", "tr")]
    uid = f"act{theme[0]}"
    H, top = 300, 96
    lx = 44

    days = sorted(d["calendar"])
    year_total = sum(c for _, c in days)
    monthly: dict[str, int] = {}
    for ds, c in days:
        monthly[ds[:7]] = monthly.get(ds[:7], 0) + c
    weekly = [(m + "-01", c) for m, c in sorted(monthly.items())]  # one point per month

    created = datetime.fromisoformat(d["created_at"].replace("Z", "+00:00"))
    years = int((datetime.now(timezone.utc) - created).days // 365.25)
    joined = t["joined"].format(n=years) if years > 1 else t["joined_one"] if years == 1 else t["joined_new"]
    school = next((v for s in cfg["sections"] for k, v in s["items"] if k in ("Okul", "School")), None)

    rows = [("pulse", t["year_total"].format(n=year_total)), ("repo", t["public_repos"].format(n=d["public_repos"])),
            ("clock", joined)] + ([("school", school)] if school else [])
    left = [f'<text x="{lx}" y="{top}" font-family="{SANS}" font-size="24" font-weight="800" fill="url(#{uid}-text)">'
            f'{esc(cfg.get("name") or d["name"])}</text>',
            f'<text x="{lx}" y="{top + 22}" fill="{p["dim"]}">@{esc(d["login"])}</text>']
    for i, (ic, text) in enumerate(rows):
        y = top + 64 + i * 32
        left.append(f'<g {fade(i)}{icon(ic, lx, y - 12, p["accent"])}'
                    f'<text x="{lx + 28}" y="{y}" fill="{p["text"]}">{esc(text)}</text></g>')

    # chart geometry
    x0, x1, y0, y1 = 430, W - 80, top + 6, H - 54  # y1 = baseline
    ymax, step = nice_max(max((c for _, c in weekly), default=0))
    n = max(len(weekly) - 1, 1)
    pts = [(x0 + (x1 - x0) * i / n, y1 - (y1 - y0) * c / ymax) for i, (_, c) in enumerate(weekly)]
    line = smooth_path(pts, y1) if len(pts) > 1 else ""
    area = f"{line} L{fmt(x1)} {y1} L{x0} {y1} Z" if line else ""

    axis = [f'<line x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}" stroke="{p["accent2"]}" stroke-opacity="0.6"/>',
            f'<line x1="{x1}" y1="{y0}" x2="{x1}" y2="{y1}" stroke="{p["accent2"]}" stroke-opacity="0.6"/>']
    for v in range(0, ymax + 1, step):
        y = y1 - (y1 - y0) * v / ymax
        axis.append(f'<line x1="{x1}" y1="{fmt(y)}" x2="{x1 + 5}" y2="{fmt(y)}" stroke="{p["accent2"]}" stroke-opacity="0.6"/>'
                    f'<text x="{x1 + 9}" y="{fmt(y + 4)}" fill="{p["dim"]}" font-size="11">{v}</text>')
        if v:
            axis.append(f'<line x1="{x0}" y1="{fmt(y)}" x2="{x1}" y2="{fmt(y)}" stroke="{p["hair"]}" stroke-dasharray="2 6"/>')
    for i, (ds, _) in enumerate(weekly):
        dt = date.fromisoformat(ds)
        if i % 2 == 0 or i == len(weekly) - 1:
            x = pts[i][0]
            axis.append(f'<line x1="{fmt(x)}" y1="{y1}" x2="{fmt(x)}" y2="{y1 + 5}" stroke="{p["accent2"]}" stroke-opacity="0.6"/>'
                        f'<text x="{fmt(x)}" y="{y1 + 20}" fill="{p["dim"]}" font-size="11" text-anchor="middle">'
                        f'{dt:%y}/{dt:%m}</text>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{t['activity_label']}">
  <title>{t['activity_label']}</title>
  <defs>{defs_common(p, uid, W, H)}
    <linearGradient id="{uid}-area" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{p['accent']}" stop-opacity="0.85"/>
      <stop offset="1" stop-color="{p['accent2']}" stop-opacity="0.12"/>
    </linearGradient>
    <clipPath id="{uid}-reveal"><rect x="{x0 - 2}" y="{y0 - 10}" width="0" height="{y1 - y0 + 12}">
      <animate attributeName="width" from="0" to="{x1 - x0 + 4}" begin="0.5s" dur="1.6s" fill="freeze"/>
    </rect></clipPath>
  </defs>
{glass_window(p, uid, W, H)}{title_bar(p, f"{cfg['username']}@github: ~/contributions")}
  <g font-family="{MONO}" font-size="13">
    {"".join(left)}
    <text x="{x1}" y="{top - 8}" fill="{p['accent2']}" font-size="12" text-anchor="end">{t['chart_label']}</text>
    {"".join(axis)}
    <g clip-path="url(#{uid}-reveal)">
      <path d="{area}" fill="url(#{uid}-area)"/>
      <path d="{line}" fill="none" stroke="{p['accent']}" stroke-width="2"/>
    </g>
  </g>
</svg>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "profile.json"))
    ap.add_argument("--data", help="render from this JSON file instead of calling the GitHub API")
    ap.add_argument("--dump", help="also save the fetched data to this JSON file")
    ap.add_argument("--only", help="comma separated cards to write: stats,activity (default: all)")
    args = ap.parse_args()
    builders = {"stats": build_stats, "activity": build_activity}
    wanted = args.only.split(",") if args.only else list(builders)

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if args.data:
        data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise SystemExit("GITHUB_TOKEN is required to fetch live data (or pass --data file.json)")
        data = fetch(cfg["username"], token)
        if args.dump:
            Path(args.dump).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in data.items() if k != "calendar"}, ensure_ascii=False))
    ASSETS.mkdir(exist_ok=True)
    for lang in LANGS:
        lc = for_lang(cfg, lang)
        for name in wanted:
            for theme in THEMES:
                (ASSETS / f"{name}-{lang}-{theme}.svg").write_text(builders[name](lc, data, theme), encoding="utf-8")
    print("Wrote:", ", ".join(f"{n}-{{en,tr}}-*.svg" for n in wanted))


if __name__ == "__main__":
    main()
