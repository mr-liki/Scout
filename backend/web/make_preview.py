#!/usr/bin/env python3
"""
make_preview.py — Build a SELF-CONTAINED preview.html.

Inlines styles.css + every JS module into one file so the whole app works
from a single HTML document (no server, works from file://). Handy for:
  - quick visual checks (open preview.html in a browser)
  - sharing a demo link / screenshot
  - hosting as a static single file

Usage:  python make_preview.py   -> writes preview.html
"""

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
JS_MODULES = ["demo.js", "store.js", "api.js", "ui.js", "main.js"]

# Classic-script rewrites for module imports.
# Function declarations hoist to the top of the bundle, so modules that are
# concatenated earlier are callable by later ones; we just need to restore the
# local binding names that `import` used to provide.
IMPORT_REWRITES = {
    "store.js": [],  # nothing imports store first
    "api.js": [
        (r'import\s*\{\s*demoSearch\s*,\s*demoHealth\s*\}\s*from\s*"[^"]+"\s*;?',
         ""),
    ],
    "ui.js": [
        (r'import\s*\*\s*as\s*store\s*from\s*"[^"]+"\s*;?',
         "const store = { loadSaved, isSaved, toggleSaved, removeSaved, loadTheme, saveTheme };"),
        (r'import\s*\{\s*searchJobs\s*as\s*apiSearchJobs\s*,\s*probeApi\s*as\s*apiProbe\s*\}\s*from\s*"[^"]+"\s*;?',
         "const apiSearchJobs = searchJobs;\nconst apiProbe = probeApi;"),
    ],
    "main.js": [
        (r'import\s*\{[^}]*\}\s*from\s*"[^"]+"\s*;?', ""),
    ],
}


def read(rel):
    with open(os.path.join(HERE, rel), "r", encoding="utf-8") as f:
        return f.read()


def main():
    html = read("index.html")
    css = read("css/styles.css")

    # Inline the stylesheet
    html = html.replace('<link rel="stylesheet" href="css/styles.css" />',
                        f"<style>\n{css}\n</style>")

    # Concatenate JS modules in dependency order, stripping module syntax
    parts = []
    for mod in JS_MODULES:
        src = read(os.path.join("js", mod))
        # Apply import rewrites for this module
        for pattern, repl in IMPORT_REWRITES.get(mod, []):
            src = re.sub(pattern, repl, src, flags=re.M)
        # Strip any remaining import/export lines
        src = re.sub(r'^\s*import\s.*?;\s*$', '', src, flags=re.M)
        src = re.sub(r'^\s*export\s+', '', src, flags=re.M)
        src = re.sub(r'^\s*export\s*\{[^}]*\}\s*;\s*$', '', src, flags=re.M)
        src = re.sub(r'^\s*export\s*\*.*?;\s*$', '', src, flags=re.M)
        parts.append(f"/* ---- {mod} ---- */\n{src}")

    bundle = "\n\n".join(parts)
    html = html.replace(
        '<script type="module" src="js/main.js"></script>',
        f"<script>\n{bundle}\n</script>",
    )

    # Force the demo banner (no API in single-file mode)
    html = html.replace('id="demoBanner" hidden',
                        'id="demoBanner" data-forced-demo')

    out = os.path.join(HERE, "preview.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {out} ({len(html)//1024} KB) — open it in any browser.")


if __name__ == "__main__":
    main()
