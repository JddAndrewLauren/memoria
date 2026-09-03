"""The one escape/unescape pair for text rendered into a durable Memoria
document (#151).

``sessions`` and ``record_extractor`` each grew their own copy of this rule
independently - a transcript turn and a decision's text both sit next to a
structural ``<a id="...">`` anchor, and both needed the same defense. The
copies agreed only because they were written days apart from the same
reasoning; nothing kept them in step, and two escaping defects were each a
case of one copy being right and the other not. This module is the one
owner: everything that writes free text next to a durable document's own
structural markup calls ``escape_entry_text`` on the way in and
``unescape_entry_text`` on the way out, and nothing re-implements the rule.

``&`` then ``<`` as entities, in that order - the exact pair ``html.unescape``
reverses without touching anything else - is the least alteration that keeps
a literal ``<`` out of the rendered text. ``>`` is deliberately left alone:
none of these documents open a new entry on ``>``, and a blockquote the
author typed (``> like this``) must still render as one.

Not every writer needs this. ``decisions.md`` entries open with
``<a id="dec-0088"></a>``, and a transcript turn's heading is
``<a id="t017"></a>`` - free text escapes there because an unescaped ``<``
could forge that boundary. ``questions.md`` has no anchors and no ids; its
only boundary is the literal ``[open] `` prefix, which escaping ``&`` and
``<`` never protected either way - so ``record_extractor.record_question``
does not call this module at all (see its docstring)."""

from __future__ import annotations

import html


def escape_entry_text(text: str) -> str:
    """``&`` then ``<`` as entities - see the module docstring for why this
    pair, this order, and why ``>`` stays untouched."""
    return text.replace("&", "&amp;").replace("<", "&lt;")


def unescape_entry_text(text: str) -> str:
    """The exact inverse of ``escape_entry_text``: ``html.unescape`` reverses
    ``&amp;`` and ``&lt;`` and nothing else, since those are the only
    entities this module ever writes."""
    return html.unescape(text)
