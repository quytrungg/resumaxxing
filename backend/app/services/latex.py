"""LaTeX rendering for the structured CV.

`render_document` is the deterministic template (used by the `mock` provider and
as the fallback when an LLM's LaTeX output is unusable). `sanitize_latex` +
`is_valid_latex` reduce LLM output to a document body, re-apply this template's
preamble and reject anything unbalanced or unsafe.
"""
import re
import unicodedata

from app.schemas import StructuredCV

# Single-column, ATS-friendly layout: no images, icons or colour blocks.
TEMPLATE_HEAD = r"""\documentclass[11pt,a4paper]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage[margin=1.5cm,top=1.4cm,bottom=1.4cm]{geometry}
\usepackage{enumitem}
\usepackage{titlesec}
\usepackage[hidelinks]{hyperref}
\pagestyle{empty}
\setlength{\parindent}{0pt}
\newcommand{\cvsection}[1]{%
  \section*{#1}%
  \vspace{-0.6em}\titlerule[0.6pt]\vspace{0.4em}%
}
\titlespacing*{\section}{0pt}{0.75em}{0.25em}
\setlist[itemize]{leftmargin=1.1em,itemsep=0.1em,topsep=0.15em,parsep=0pt}
"""

TEMPLATE_TAIL = "\\end{document}\n"

_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

_REQUIRED_MARKERS = (r"\documentclass", r"\begin{document}", r"\end{document}")

_ENVIRONMENT = re.compile(r"\\(begin|end)\{([A-Za-z*]+)\}")

# Primitives that can read, write or execute while compiling.
_DANGEROUS = re.compile(
    r"\\(?:write18|input\b|include\b|openout\b|openin\b|read\b|immediate\b"
    r"|catcode\b|newwrite\b|shellesc\b)"
)

# Typographic characters that pdflatex + inputenc does not cover reliably.
_TYPOGRAPHIC = {
    "\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"', "\u2022": "-", "\u25cf": "-",
    "\u00b7": "-", "\u2026": "...", "\u00a0": " ", "\u2192": "->",
}


def _to_ascii(text: str) -> str:
    """Keep the deterministic template compilable with pdflatex (ASCII only)."""
    for char, replacement in _TYPOGRAPHIC.items():
        text = text.replace(char, replacement)
    decomposed = unicodedata.normalize("NFKD", text)
    return decomposed.encode("ascii", "ignore").decode("ascii")


def escape_latex(text: str) -> str:
    return "".join(_ESCAPES.get(ch, ch) for ch in _to_ascii(text))


def _environments_balanced(text: str) -> bool:
    stack = []
    for match in _ENVIRONMENT.finditer(text):
        kind, name = match.group(1), match.group(2)
        if kind == "begin":
            stack.append(name)
        elif not stack or stack.pop() != name:
            return False
    return not stack


def _braces_balanced(text: str) -> bool:
    cleaned = re.sub(r"\\[{}]", "", text)
    return cleaned.count("{") == cleaned.count("}")


def is_valid_latex(source: str) -> bool:
    """A self-contained document we are willing to hand to the user."""
    if not source or not all(m in source for m in _REQUIRED_MARKERS):
        return False
    if _DANGEROUS.search(source):
        return False
    return _environments_balanced(source) and _braces_balanced(source)


def sanitize_latex(source: str) -> str:
    """Reduce LLM output to the document body and re-apply our known-good
    preamble, so the layout (and the packages it needs) never depends on the
    model. Returns "" when no document body is present."""
    text = (source or "").replace("\r\n", "\n")
    text = re.sub(r"```[a-zA-Z]*", "", text)
    start = text.find(r"\begin{document}")
    end = text.rfind(r"\end{document}")
    if start == -1 or end == -1 or end <= start:
        return ""
    body = text[start + len(r"\begin{document}"):end].strip("\n")
    return f"{TEMPLATE_HEAD}\n\\begin{{document}}\n{body}\n{TEMPLATE_TAIL}"


def render_document(cv: StructuredCV) -> str:
    """Deterministic LaTeX source for a structured CV."""
    lines = [TEMPLATE_HEAD, r"\begin{document}", ""]

    header = []
    if cv.name:
        header.append(r"{\LARGE\bfseries " + escape_latex(cv.name) + r"}\\[2pt]")
    if cv.headline:
        header.append(r"{\large " + escape_latex(cv.headline) + r"}\\[3pt]")
    if cv.contact:
        header.append(
            r"{" + r" $\mid$ ".join(escape_latex(c) for c in cv.contact) + r"}"
        )
    if header:
        lines.extend([r"\begin{center}", *header, r"\end{center}", ""])

    for section in cv.sections:
        lines.append(r"\cvsection{" + escape_latex(section.heading.upper()) + "}")
        if section.bullets:
            lines.append(r"\begin{itemize}")
            for bullet in section.bullets:
                lines.append(r"  \item " + escape_latex(bullet))
            lines.append(r"\end{itemize}")
        lines.append("")

    if not cv.sections:  # nothing but the header (or nothing at all)
        lines.append(r"\cvsection{Summary}")
        lines.append(r"\begin{itemize}")
        lines.append(r"  \item (empty document)")
        lines.append(r"\end{itemize}")
        lines.append("")

    lines.append(TEMPLATE_TAIL)
    return "\n".join(lines)
