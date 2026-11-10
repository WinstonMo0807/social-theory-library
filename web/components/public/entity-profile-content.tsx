import { profileFields, type IdentityProfile } from "@/lib/knowledge-profiles";

export function EntityProfileContent({ kind, profile }: { kind: string; profile?: IdentityProfile | null }) {
  if (!profile) return null;
  const fields = (profileFields[kind] || []).filter(f => profile[f.key] !== undefined && profile[f.key] !== null && profile[f.key] !== "");
  if (!fields.length) return null;
  return <dl className="knowledge-identity-profile">{fields.map(field => <div key={field.key}><dt>{field.label}</dt><dd>{field.options?.[String(profile[field.key])] || profile[field.key]}</dd></div>)}</dl>;
}
