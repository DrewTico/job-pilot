"""Shared deterministic writing checks, with no model or storage dependencies."""

import re


_BANNED_STYLE = (
    # CLAUDE.md writing rules, followed by stricter existing screening rules.
    "passionate", "synergy", "I am excited to apply", "thrilled",
    "fast-paced", "I hope this email finds you well", "dynamic", "go-getter",
    "leverage", "spearheaded", "passionate about", "excited to", "deep dive",
    "robust", "seamless", "cutting-edge", "in today's landscape", "i thrive",
    "wealth of experience", "delve", "testament", "underscore",
)
# whole-word, stem-tolerant ("leveraged", "underscores"), flexible whitespace
_BANNED_STYLE_RES = tuple(
    (phrase, re.compile(r"\b" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\w*",
                        re.IGNORECASE))
    for phrase in _BANNED_STYLE)
_NOT_ONLY_BUT = re.compile(
    r"\bnot\s+(?:only|just)\b[^.?!]{0,120}?\bbut\b", re.IGNORECASE | re.DOTALL)


def lint_writing(text: str) -> list[str]:
    """Return mechanical writing violations; an empty list means clean.

    Callers must treat a nonempty result as failed writing validation. This
    pure function does not rewrite content or grant approval. It is reusable
    by screening and future packet validation, but does not check factual
    grounding or context-dependent writing rules.

    Both dash characters are rejected everywhere, including numeric ranges,
    preserving the existing screening gate's stricter behavior.
    """
    violations: list[str] = []
    if "—" in text or "–" in text:
        violations.append("style: em/en dash (use a period or a comma)")
    for phrase, pattern in _BANNED_STYLE_RES:
        if pattern.search(text):
            violations.append(f"style: banned phrase {phrase!r}")
    if _NOT_ONLY_BUT.search(text):
        violations.append("style: 'not only/just X but Y' construction")
    return violations
