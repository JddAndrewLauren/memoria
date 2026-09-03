"""The one escape/inverse pair every durable-document writer shares (#151)."""

from memoria.entity_escape import escape_entry_text, unescape_entry_text


def test_escape_then_unescape_round_trips_markup_and_an_anchor_fragment():
    text = 'a < b && c > d, and a literal &lt; too, next to <a id="dec-0088"></a>'

    escaped = escape_entry_text(text)

    assert "<" not in escaped
    assert unescape_entry_text(escaped) == text


def test_escape_leaves_a_typed_blockquote_marker_untouched():
    assert escape_entry_text("> like this") == "> like this"
