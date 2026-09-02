import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { readSource, ApiError } from "../api/client";
import { Badge } from "../components/Badge";

/**
 * A basic read of one source - frontmatter and verbatim paragraphs. The
 * citation slide-over, apparatus rendering and "Open original" belong to
 * #25; this page is what #24 needs so a source in the tree resolves to
 * something readable.
 */
export default function SourceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["source", id],
    queryFn: () => readSource(id as string),
    enabled: Boolean(id),
  });

  if (isLoading) return <p className="p-8 text-sm text-muted">Loading...</p>;
  if (isError) {
    const message = error instanceof ApiError ? error.message : "This source could not be read.";
    return <p className="p-8 text-sm text-muted">{message}</p>;
  }
  if (!data) return null;

  return (
    <article className="p-8">
      <header className="mb-6 flex flex-wrap items-center gap-2">
        <h1 className="font-mono text-sm text-ink">{data.id}</h1>
        <Badge tone={data.contemporaneous ? "green" : "amber"}>
          {data.contemporaneous ? "Contemporaneous" : "Retrospective"}
        </Badge>
        <Badge tone="neutral">recorded {data.recorded_date}</Badge>
        <Badge tone="neutral">
          event {data.event_date} - {data.date_confidence}
        </Badge>
        <Badge tone="neutral">{data.source_type}</Badge>
      </header>
      <div className="prose">
        {data.paragraphs.map((paragraph) => (
          <p key={paragraph.anchor} id={paragraph.anchor}>
            <span className="anchor" aria-hidden="true">
              {paragraph.anchor.split("-p").pop()}
            </span>
            {paragraph.text}
          </p>
        ))}
      </div>
    </article>
  );
}
