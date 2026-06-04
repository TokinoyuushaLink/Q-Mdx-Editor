from __future__ import annotations
from themes import THEMES

_CSS_TEMPLATE = """
html, body {{
    background: {bg};
    color: {fg};
    font-family: {font_stack};
    font-size: {font_size};
    line-height: 1.65;
    margin: 0;
    padding: 12px 14px;
}}
h2, h3 {{
    font-size: 1.4em; font-weight: bold;
    margin: 0 0 4px 0;
    color: {heading};
}}
h5 {{
    font-size: 0.88em; font-weight: normal;
    margin: 4px 0 1px 0;
    color: {muted2};
}}
b, .hw, span.hw {{
    font-size: 1.4em; font-weight: bold;
    color: {heading};
}}
.h-g .hw {{ display: inline; font-size: inherit; }}
pron, .pr, .phon-gb, .phon-us {{
    font-size: 0.88em;
    color: {muted};
}}
.pos, .class {{
    font-style: italic;
    font-size: 0.9em;
    color: {muted};
}}
.zh, .chn {{ color: {chinese}; }}
.df        {{ color: {fg}; }}
.sense     {{ margin: 3px 0; }}
p.ex, .eg, .def-sentence-from {{
    margin-left: 14px;
    font-size: 0.9em;
    color: {example};
}}
.def-sentence-to {{
    margin-left: 14px;
    font-size: 0.87em;
    color: {muted};
}}
a {{ color: {link}; text-decoration: none; }}
b.num {{ color: {muted2}; }}
dl {{ margin: 0; }}
dt {{ font-weight: bold; margin-top: 6px; }}
dd {{ margin-left: 12px; }}
dd:empty {{ display: none; }}
ol.info-list {{
    margin: 0; padding-left: 0;
    list-style: none;
}}
ol.info-list > li {{ margin: 2px 0; padding: 0; }}
.info-cite {{ margin: 1px 0 1px 14px; }}
i.number {{
    font-style: normal;
    color: {muted2};
    font-size: 0.85em;
    margin-right: 3px;
}}
p.gray  {{ font-size: 0.88em; }}
img, table, pre {{ max-width: 100%; }}

/* Markdown-rendered elements */
strong {{ font-weight: bold; }}
em {{ font-style: italic; }}
blockquote {{
    margin: 3px 0 3px 14px;
    padding-left: 8px;
    border-left: 3px solid {muted2};
    color: {muted};
}}
code {{
    font-family: "Consolas", "Courier New", monospace;
    font-size: 0.88em;
    color: {example};
}}
pre {{
    font-family: "Consolas", "Courier New", monospace;
    font-size: 0.88em;
    margin-left: 14px;
    color: {example};
}}
table {{ border-collapse: collapse; margin: 4px 0; }}
th, td {{ border: 1px solid {muted2}; padding: 2px 8px; }}
th {{ font-weight: bold; background-color: {bg}; }}

/* Hide layout noise from MDX */
a[href^="sound://"], .btn-sound,
img[src="uk_pron.png"], img[src="us_pron.png"],
ranks {{ display: none; }}
"""

_PALETTES = {
    "light": dict(
        bg="#ffffff",    fg="#1a1a1a",   heading="#111111",
        muted="#666666", muted2="#888888", chinese="#444444",
        example="#555555", link="#0066cc",
    ),
    "dark": dict(
        bg="#1e1e1e",    fg="#e0e0e0",   heading="#f0f0f0",
        muted="#aaaaaa", muted2="#888888", chinese="#cccccc",
        example="#aaaaaa", link="#6699ff",
    ),
    "sepia": dict(
        bg="#fbf7f0",    fg="#3c3228",   heading="#2a1e14",
        muted="#7a6a60", muted2="#8a7a70", chinese="#4a3a30",
        example="#6a5a50", link="#7b5b35",
    ),
}


_DEFAULT_FONT_STACK = '"Segoe UI", "Microsoft YaHei", "Helvetica Neue", sans-serif'


def get_css(theme: str = "light", font_family: str = "", font_size: float = 14.0) -> str:
    stack = f'"{font_family}", {_DEFAULT_FONT_STACK}' if font_family else _DEFAULT_FONT_STACK
    return _CSS_TEMPLATE.format(
        font_stack=stack,
        font_size=f"{font_size:.0f}px",
        **_PALETTES.get(theme, _PALETTES["light"]),
    )
