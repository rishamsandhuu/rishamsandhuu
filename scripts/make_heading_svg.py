#!/usr/bin/env python3
"""
One lowercase-mono heading, styled the way the rest of the page is:
a small label on the left and a hairline rule running to the right edge.

Usage:
    python3 scripts/make_heading_svg.py "selected work" assets/h-selected-work.svg
    python3 scripts/make_heading_svg.py --width 880 "tech" assets/h-tech.svg

alt text carries the heading text for screen readers, since an <img>
heading has no entry in GitHub's outline/anchor list -- that's the one
real cost of doing headings this way.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from fontutil import font_face_css

FG_LIGHT = "#24292f"
RULE_LIGHT = "#d0d7de"
FG_DARK = "#e6edf3"
RULE_DARK = "#30363d"
FONT_SIZE = 15
CHAR_W_BOLD_ESTIMATE = 8.6  # JetBrains Mono bold is a touch wider than 0.6em


def build(label, out_path, width=880, height=34):
    css, family = font_face_css("h", 700, "basic-bold.woff2")
    text_w = len(label) * CHAR_W_BOLD_ESTIMATE
    rule_x = 14 + text_w + 14
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"
viewBox="0 0 {width} {height}" role="img" aria-label="{label} section heading">
<style>
{css}
.lbl{{font-family:'{family}',ui-monospace,monospace;font-size:{FONT_SIZE}px;
     letter-spacing:.5px;fill:{FG_LIGHT}}}
.rule{{stroke:{RULE_LIGHT};stroke-width:1}}
@media(prefers-color-scheme:dark){{
  .lbl{{fill:{FG_DARK}}}
  .rule{{stroke:{RULE_DARK}}}
}}
</style>
<text x="0" y="{height/2 + FONT_SIZE/3:.1f}" class="lbl">{label}</text>
<line x1="{rule_x:.1f}" y1="{height/2:.1f}" x2="{width}" y2="{height/2:.1f}" class="rule"/>
</svg>'''
    with open(out_path, "w") as f:
        f.write(svg)
    return out_path


if __name__ == "__main__":
    args = sys.argv[1:]
    width = 880
    if "--width" in args:
        i = args.index("--width")
        width = int(args[i + 1])
        del args[i:i + 2]
    label, out_path = args[0], args[1]
    build(label, out_path, width=width)
    print(f"wrote {out_path}")
