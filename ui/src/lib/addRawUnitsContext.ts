import { createContext, useContext } from "react";
import type { PickedFile } from "./rawUnits";

/**
 * Opening the Add sources dialog from anywhere (ADR-0013): the SOURCES
 * tree, the Ingestion page and the window-wide drop all reach the one
 * dialog App mounts. The default is a no-op so a tree or page renders
 * outside App - in its own tests - with the button present and inert.
 */
export const AddRawUnitsContext = createContext<(files?: PickedFile[]) => void>(() => {});

export function useOpenAddRawUnits(): (files?: PickedFile[]) => void {
  return useContext(AddRawUnitsContext);
}
