"use client";
import { AcademicRelations } from "../academic-relations";
export function ScholarPersonRelations({ scholarId, blocked }: { scholarId: string; blocked: boolean; onChanged: () => void }) {
  return <AcademicRelations legacyType="scholar" legacyId={scholarId} blocked={blocked} />;
}
