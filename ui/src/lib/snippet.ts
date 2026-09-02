// A search hit's snippet wraps matched terms in
// `memoria.index.SNIPPET_MATCH_START`/`_END` (`\x01`/`\x02`) - "a client
// splits on those marks; it never renders the snippet as markup"
// (src/memoria/web/schemas.py's SearchResultOut docstring). This is that
// split, turning the marks into structured parts a component renders as
// React nodes, never as injected HTML.
const START = "\x01";
const END = "\x02";

export interface SnippetPart {
  text: string;
  matched: boolean;
}

export function splitSnippet(snippet: string): SnippetPart[] {
  const parts: SnippetPart[] = [];
  let rest = snippet;
  for (;;) {
    const startIndex = rest.indexOf(START);
    if (startIndex === -1) {
      if (rest) parts.push({ text: rest, matched: false });
      return parts;
    }
    if (startIndex > 0) parts.push({ text: rest.slice(0, startIndex), matched: false });
    const afterStart = rest.slice(startIndex + START.length);
    const endIndex = afterStart.indexOf(END);
    if (endIndex === -1) {
      // No closing mark - not expected from the server, but keep the text
      // visible rather than dropping it.
      parts.push({ text: afterStart, matched: false });
      return parts;
    }
    parts.push({ text: afterStart.slice(0, endIndex), matched: true });
    rest = afterStart.slice(endIndex + END.length);
  }
}
