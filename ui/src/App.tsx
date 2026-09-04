import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { SearchDialog } from "./components/SearchDialog";
import { SettingsDialog } from "./components/SettingsDialog";
import { NewSectionButton } from "./components/NewSectionButton";
import { NewSectionDialog } from "./components/NewSectionDialog";
import { CitationPanelProvider } from "./components/CitationPanel";

export default function App() {
  const [searchOpen, setSearchOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [newSectionOpen, setNewSectionOpen] = useState(false);

  return (
    <CitationPanelProvider>
      <div className="flex min-h-screen">
        <Sidebar
          onOpenSearch={() => setSearchOpen(true)}
          onOpenSettings={() => setSettingsOpen(true)}
        />
        <main className="flex-1 overflow-y-auto bg-card">
          <Outlet />
        </main>
        <SearchDialog open={searchOpen} onClose={() => setSearchOpen(false)} />
        <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />
        {/* ADR-0011: the floating `+ New section` and its dialog, from anywhere. */}
        <NewSectionButton onClick={() => setNewSectionOpen(true)} />
        <NewSectionDialog open={newSectionOpen} onClose={() => setNewSectionOpen(false)} />
      </div>
    </CitationPanelProvider>
  );
}
