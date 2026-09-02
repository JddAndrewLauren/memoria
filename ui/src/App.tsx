import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { SearchDialog } from "./components/SearchDialog";
import { CitationPanelProvider } from "./components/CitationPanel";

export default function App() {
  const [searchOpen, setSearchOpen] = useState(false);

  return (
    <CitationPanelProvider>
      <div className="flex min-h-screen">
        <Sidebar onOpenSearch={() => setSearchOpen(true)} />
        <main className="flex-1 overflow-y-auto bg-card">
          <Outlet />
        </main>
        <SearchDialog open={searchOpen} onClose={() => setSearchOpen(false)} />
      </div>
    </CitationPanelProvider>
  );
}
