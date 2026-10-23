import type { ReactNode } from "react";
import { PlacementSelectionProvider } from "@/components/admin/curation/placement-selection-session";

export default function ContentLayout({children}:{children:ReactNode}) {
  return <PlacementSelectionProvider>{children}</PlacementSelectionProvider>;
}
