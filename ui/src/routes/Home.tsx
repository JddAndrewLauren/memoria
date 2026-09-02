export default function Home() {
  return (
    <div className="p-8">
      <h1 className="font-serif text-2xl text-ink">Memoria</h1>
      <p className="mt-3 max-w-[480px] text-sm text-secondary">
        Select a source from SOURCES, or an entry under SUBJECTS, to read it. Press the
        search glyph in the sidebar to search across sources and subjects.
      </p>
    </div>
  );
}
