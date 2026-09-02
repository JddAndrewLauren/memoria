import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { readRawSource, ApiError } from "../api/client";

/**
 * "Open original" (#25): the un-normalized file `original_file` was
 * normalized from, served in the browser exactly as it arrived - no
 * highlight, no scroll position, no line anchor, because `original_locator`
 * is a human-readable pointer a person follows, never a byte offset
 * (docs/normalized-record-schema.md). Opened in its own tab so the reading
 * surface underneath it is never navigated away from.
 */
export default function RawSourcePage() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["source-raw", id],
    queryFn: () => readRawSource(id as string),
    enabled: Boolean(id),
  });

  if (isLoading) return <p className="p-8 text-sm text-muted">Loading...</p>;
  if (isError) {
    const message =
      error instanceof ApiError ? error.message : "The original file could not be read.";
    return <p className="p-8 text-sm text-muted">{message}</p>;
  }
  if (!data) return null;

  return (
    <article className="p-8">
      <header className="mb-6">
        <div className="font-mono text-[10px] uppercase tracking-wide text-muted">
          Original locator
        </div>
        <p className="text-sm text-ink">{data.original_locator}</p>
      </header>
      <pre className="max-w-[720px] whitespace-pre-wrap break-words font-mono text-sm text-body">
        {data.text}
      </pre>
    </article>
  );
}
