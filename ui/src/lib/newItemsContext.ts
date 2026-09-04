import { createContext, useContext } from "react";

/**
 * The two creates a tree can open - the New section dialog (ADR-0012) and
 * the New subject dialog (ADR-0014). App owns both dialogs; a tree row
 * calls one of these, the way `AddRawUnitsContext` opens Add sources.
 */
export interface NewItems {
  openNewSection: () => void;
  openNewSubject: () => void;
}

export const NewItemsContext = createContext<NewItems>({
  openNewSection: () => {},
  openNewSubject: () => {},
});

export function useNewItems(): NewItems {
  return useContext(NewItemsContext);
}
