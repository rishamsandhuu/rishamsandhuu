"""
Tiny stdlib-only helper for inlining a woff2 font as a base64 data URI.

Why this exists: GitHub's README sanitizer strips <link> and any external
@font-face src, and these SVGs are loaded via <img> so they can't reach out
for a stylesheet anyway. The only font that survives is one baked into the
file itself. Keep it stdlib-only (no fontTools import here) so
generate_stats.py can run in CI with zero pip installs.
"""
import base64
import os

ASSETS_FONTS = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")


def font_face_css(class_name, weight, woff2_filename):
    """Return an @font-face + class rule with the font inlined as base64."""
    path = os.path.join(ASSETS_FONTS, woff2_filename)
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    family = f"pf-{weight}-{abs(hash(woff2_filename)) % 9999}"
    return (
        f"@font-face{{font-family:'{family}';font-weight:{weight};"
        f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}"
        f".{class_name}{{font-family:'{family}',ui-monospace,monospace;}}"
    ), family
