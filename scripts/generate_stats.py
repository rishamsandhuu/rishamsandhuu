#!/usr/bin/env python3
"""
Draws stats.svg, streak.svg, langs.svg, year.svg from the GitHub API.

Standard library only -- this runs inside GitHub Actions on the built-in
GITHUB_TOKEN, so there's nothing to pip install and nothing that can break
in CI beyond the network call itself.

Env vars:
    GITHUB_TOKEN   provided automatically by Actions (contents: read is enough)
    GH_LOGIN       provided automatically as github.repository_owner

Run locally for testing with a personal token:
    GITHUB_TOKEN=ghp_xxx GH_LOGIN=yourname python3 scripts/generate_stats.py
"""
import os
import sys
import json
import base64
import datetime as dt
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(__file__))
from fontutil import font_face_css

RAMP = " .`:-=+*cs#%@"
FG_LIGHT = "#57606a"
DIM_LIGHT = "#8c959f"
RULE_LIGHT = "#d0d7de"
FG_DARK = "#c9d1d9"
DIM_DARK = "#8b949e"
RULE_DARK = "#30363d"
ACCENT_LIGHT = "#24292f"
ACCENT_DARK = "#e6edf3"

API = "https://api.github.com/graphql"
REST = "https://api.github.com"


def gh_graphql(token, query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(API, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def gh_rest(token, path):
    req = urllib.request.Request(f"{REST}{path}")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


# ---------------------------------------------------------------- contributions

CONTRIB_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date contributionCount }
        }
      }
    }
  }
}
"""


def fetch_contributions(token, login):
    # Pin to whole UTC days. Left to "the past year" from request time, two
    # runs minutes apart bucket days into different weeks and the sparkline
    # shifts by a fraction of a pixel every single night.
    today = dt.datetime.now(dt.timezone.utc).replace(hour=23, minute=59, second=59, microsecond=0)
    start = (today - dt.timedelta(days=364)).replace(hour=0, minute=0, second=0)
    data = gh_graphql(token, CONTRIB_QUERY, {
        "login": login,
        "from": start.isoformat(),
        "to": today.isoformat(),
    })
    cal = data["user"]["contributionsCollection"]["contributionCalendar"]
    weeks = cal["weeks"]
    days = [d for w in weeks for d in w["contributionDays"]]
    return cal["totalContributions"], weeks, days


def weekly_totals(weeks):
    return [sum(d["contributionCount"] for d in w["contributionDays"]) for w in weeks]


def compute_streaks(days):
    counts = [d["contributionCount"] for d in days]
    dates = [d["date"] for d in days]
    longest = cur = 0
    longest_range = cur_start = None
    run_start_idx = None
    for i, c in enumerate(counts):
        if c > 0:
            if cur == 0:
                run_start_idx = i
            cur += 1
            if cur > longest:
                longest = cur
                longest_range = (dates[run_start_idx], dates[i])
        else:
            cur = 0
    # current streak = trailing run ending at the last day with data
    cur_streak = 0
    cur_end_idx = len(counts) - 1
    i = cur_end_idx
    while i >= 0 and counts[i] > 0:
        cur_streak += 1
        i -= 1
    cur_range = (dates[i + 1], dates[cur_end_idx]) if cur_streak else None
    return {
        "current": cur_streak, "current_range": cur_range,
        "longest": longest, "longest_range": longest_range,
    }


# -------------------------------------------------------------------- languages

REPOS_QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    repositories(first: 50, after: $after, privacy: PUBLIC, ownerAffiliations: OWNER, isFork: false) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def fetch_languages(token, login):
    by_bytes = {}
    by_repo = {}
    colors = {}
    after = None
    while True:
        data = gh_graphql(token, REPOS_QUERY, {"login": login, "after": after})
        repos = data["user"]["repositories"]
        for repo in repos["nodes"]:
            seen_in_repo = set()
            for edge in repo["languages"]["edges"]:
                name = edge["node"]["name"]
                colors[name] = edge["node"]["color"] or "#8c959f"
                by_bytes[name] = by_bytes.get(name, 0) + edge["size"]
                seen_in_repo.add(name)
            for name in seen_in_repo:
                by_repo[name] = by_repo.get(name, 0) + 1
        if not repos["pageInfo"]["hasNextPage"]:
            break
        after = repos["pageInfo"]["endCursor"]
    return by_bytes, by_repo, colors


# ------------------------------------------------------------------------- svg

def _style_block(extra_classes=""):
    css_reg, fam_reg = font_face_css("t", 400, "basic-regular.woff2")
    css_bold, fam_bold = font_face_css("tb", 700, "basic-bold.woff2")
    return f"""<style>
{css_reg}
{css_bold}
text{{font-family:'{fam_reg}',ui-monospace,monospace}}
.b{{font-family:'{fam_bold}',ui-monospace,monospace}}
.fg{{fill:{FG_LIGHT}}} .dim{{fill:{DIM_LIGHT}}} .strong{{fill:{ACCENT_LIGHT}}}
.rule{{stroke:{RULE_LIGHT}}} .bar{{fill:{FG_LIGHT}}}
@media(prefers-color-scheme:dark){{
  .fg{{fill:{FG_DARK}}} .dim{{fill:{DIM_DARK}}} .strong{{fill:{ACCENT_DARK}}}
  .rule{{stroke:{RULE_DARK}}} .bar{{fill:{FG_DARK}}}
}}
{extra_classes}
</style>"""


def build_stats_svg(total, weeks, out_path, width=430, height=140):
    totals = weekly_totals(weeks)
    n = len(totals)
    mx = max(totals) or 1
    pad_l, pad_r, pad_t, pad_b = 16, 16, 44, 20
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    bar_w = plot_w / n * 0.7
    gap = plot_w / n
    bars = []
    for i, v in enumerate(totals):
        h = (v / mx) * plot_h if mx else 0
        x = pad_l + i * gap + (gap - bar_w) / 2
        y = pad_t + (plot_h - h)
        bars.append(f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{max(h,1):.1f}" rx="1" opacity="0.85"/>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{total} contributions in the last year">
{_style_block()}
<text x="16" y="26" class="b strong" font-size="22">{total:,}</text>
<text x="16" y="40" class="dim" font-size="11">contributions, past 12 months</text>
{''.join(bars)}
<line x1="{pad_l}" y1="{pad_t+plot_h}" x2="{width-pad_r}" y2="{pad_t+plot_h}" class="rule" stroke-width="1"/>
</svg>'''
    open(out_path, "w").write(svg)


def build_streak_svg(streaks, out_path, width=430, height=100):
    def fmt(r):
        if not r:
            return "--"
        a, b = r
        return f"{a[5:]} to {b[5:]}"
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="streaks">
{_style_block()}
<text x="16" y="30" class="dim" font-size="11">current streak</text>
<text x="16" y="54" class="b strong" font-size="22">{streaks['current']}d</text>
<text x="16" y="70" class="dim" font-size="10">{fmt(streaks['current_range'])}</text>

<line x1="{width/2:.1f}" y1="14" x2="{width/2:.1f}" y2="{height-14}" class="rule" stroke-width="1"/>

<text x="{width/2+20:.1f}" y="30" class="dim" font-size="11">longest streak</text>
<text x="{width/2+20:.1f}" y="54" class="b strong" font-size="22">{streaks['longest']}d</text>
<text x="{width/2+20:.1f}" y="70" class="dim" font-size="10">{fmt(streaks['longest_range'])}</text>
</svg>'''
    open(out_path, "w").write(svg)


def build_langs_svg(by_bytes, out_path, width=430, top_n=6):
    total = sum(by_bytes.values()) or 1
    ranked = sorted(by_bytes.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    row_h = 22
    pad_t = 34
    height = pad_t + row_h * len(ranked) + 14
    rows = []
    for i, (name, size) in enumerate(ranked):
        pct = size / total * 100
        y = pad_t + i * row_h
        bar_max = width - 32 - 60
        bar_w = bar_max * (pct / 100)
        rows.append(
            f'<text x="16" y="{y+13}" class="fg" font-size="12">{name}</text>'
            f'<rect x="120" y="{y+2}" width="{bar_max}" height="8" rx="4" class="rule" fill="{RULE_LIGHT}" opacity="0.5"/>'
            f'<rect x="120" y="{y+2}" width="{max(bar_w,2):.1f}" height="8" rx="4" class="bar"/>'
            f'<text x="{120+bar_max+8}" y="{y+11}" class="dim" font-size="11">{pct:.1f}%</text>'
        )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="top languages by bytes">
{_style_block()}
<text x="16" y="20" class="dim" font-size="11">top languages, by bytes written</text>
{''.join(rows)}
</svg>'''
    open(out_path, "w").write(svg)


def build_year_svg(days, out_path, width=900):
    """One character per day, using the portrait's own ramp -- the whole
    year at a glance in the exact typographic language as the rest of the page."""
    counts = [d["contributionCount"] for d in days]
    mx = max(counts) or 1
    thresholds = [0, mx * 0.15, mx * 0.35, mx * 0.6, mx * 0.85]
    chars = " .-=*#"  # short ramp, sparse->dense, 0 maps to blank

    def char_for(c):
        if c == 0:
            return chars[0]
        for i in range(len(thresholds) - 1, -1, -1):
            if c >= thresholds[i]:
                return chars[min(i + 1, len(chars) - 1)]
        return chars[1]

    weeks = [days[i:i + 7] for i in range(0, len(days), 7)]
    cols = len(weeks)
    char_w = 10
    row_h = 12
    pad = 16
    plot_w = cols * char_w
    css, fam = font_face_css("y", 400, "ramp.woff2")
    rows = []
    for col, week in enumerate(weeks):
        for row, day in enumerate(week):
            ch = char_for(day["contributionCount"])
            if ch == " ":
                continue
            x = pad + col * char_w
            y = pad + row * row_h + 9
            rows.append(f'<text x="{x}" y="{y}" class="yc" font-size="12">{ch}</text>')
    height = pad * 2 + 7 * row_h
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{plot_w+pad*2}" height="{height}" viewBox="0 0 {plot_w+pad*2} {height}" role="img" aria-label="contributions through the year, one character per day">
<style>
{css}
.yc{{font-family:'{fam}',ui-monospace,monospace;fill:{FG_LIGHT}}}
@media(prefers-color-scheme:dark){{.yc{{fill:{FG_DARK}}}}}
</style>
{''.join(rows)}
</svg>'''
    open(out_path, "w").write(svg)


def main():
    token = os.environ.get("GITHUB_TOKEN")
    login = os.environ.get("GH_LOGIN")
    if not token or not login:
        print("Set GITHUB_TOKEN and GH_LOGIN", file=sys.stderr)
        sys.exit(1)

    out_dir = os.path.join(os.path.dirname(__file__), "..", "assets")
    os.makedirs(out_dir, exist_ok=True)

    total, weeks, days = fetch_contributions(token, login)
    streaks = compute_streaks(days)
    by_bytes, by_repo, colors = fetch_languages(token, login)

    build_stats_svg(total, weeks, os.path.join(out_dir, "stats.svg"))
    build_streak_svg(streaks, os.path.join(out_dir, "streak.svg"))
    build_langs_svg(by_bytes, os.path.join(out_dir, "langs.svg"))
    build_year_svg(days, os.path.join(out_dir, "year.svg"))
    print(f"total={total} current_streak={streaks['current']} longest_streak={streaks['longest']}")
    print("wrote assets/stats.svg assets/streak.svg assets/langs.svg assets/year.svg")


if __name__ == "__main__":
    main()
