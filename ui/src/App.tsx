import { useCallback, useMemo, useState } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { SearchDialog } from "./components/SearchDialog";
import { SettingsDialog } from "./components/SettingsDialog";
import { NewSectionButton } from "./components/NewSectionButton";
import { NewSectionDialog } from "./components/NewSectionDialog";
import { NewSubjectDialog } from "./components/NewSubjectDialog";
import { CitationPanelProvider } from "./components/CitationPanel";
import { AddRawUnitsDialog } from "./components/AddRawUnitsDialog";
import { WindowDropZone } from "./components/WindowDropZone";
import { AddRawUnitsContext } from "./lib/addRawUnitsContext";
import { NewItemsContext, type NewItems } from "./lib/newItemsContext";
import type { PickedFile } from "./lib/rawUnits";

export default function App() {
  const [searchOpen, setSearchOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [newSectionOpen, setNewSectionOpen] = useState(false);
  const [newSubjectOpen, setNewSubjectOpen] = useState(false);
  // ADR-0014: the trees' create rows open the same two dialogs.
  const newItems = useMemo<NewItems>(
    () => ({
      openNewSection: () => setNewSectionOpen(true),
      openNewSubject: () => setNewSubjectOpen(true),
    }),
    [],
  );
  // ADR-0013: the Add sources dialog and its list. App owns the list so a
  // drop anywhere - the dialog open or not - lands in it; `session` remounts
  // the dialog per opening so a finished batch does not linger.
  const [addOpen, setAddOpen] = useState(false);
  const [addSession, setAddSession] = useState(0);
  const [addFiles, setAddFiles] = useState<PickedFile[]>([]);
  const appendFiles = useCallback((files: PickedFile[]) => {
    setAddFiles((current) => {
      const seen = new Set(current.map((row) => row.path));
      return [...current, ...files.filter((row) => !seen.has(row.path))];
    });
  }, []);
  const openAddRawUnits = useCallback(
    (files: PickedFile[] = []) => {
      if (addOpen) {
        appendFiles(files);
        return;
      }
      setAddSession((value) => value + 1);
      setAddFiles(files);
      setAddOpen(true);
    },
    [addOpen, appendFiles],
  );

  return (
    <CitationPanelProvider>
      <AddRawUnitsContext.Provider value={openAddRawUnits}>
        <NewItemsContext.Provider value={newItems}>
          <div className="flex h-screen overflow-hidden">
            <Sidebar
              onOpenSearch={() => setSearchOpen(true)}
              onOpenSettings={() => setSettingsOpen(true)}
            />
            <main className="flex-1 overflow-y-auto bg-card">
              <Outlet />
            </main>
            <SearchDialog
              open={searchOpen}
              onClose={() => setSearchOpen(false)}
            />
            <SettingsDialog
              open={settingsOpen}
              onClose={() => setSettingsOpen(false)}
            />
            {/* ADR-0012: the floating `+ New section` and its dialog, from anywhere. */}
            <NewSectionButton onClick={() => setNewSectionOpen(true)} />
            <NewSectionDialog
              open={newSectionOpen}
              onClose={() => setNewSectionOpen(false)}
            />
            <NewSubjectDialog
              open={newSubjectOpen}
              onClose={() => setNewSubjectOpen(false)}
            />
            <WindowDropZone onFiles={openAddRawUnits} />
            <AddRawUnitsDialog
              key={addSession}
              open={addOpen}
              onClose={() => setAddOpen(false)}
              files={addFiles}
              onAddFiles={appendFiles}
            />
          </div>
        </NewItemsContext.Provider>
      </AddRawUnitsContext.Provider>
    </CitationPanelProvider>
  );
}
