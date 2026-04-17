/**
 * Category slug derivation — keep this mirror-synced with backend taxonomy.
 * Canonical 8: CorpFin, SCS III, APES, E4E, Baseball, Recruiting, Projects, Life.
 * Slug rule: lowercase + strip all non-alphanumerics. "SCS III" -> "scsiii".
 */
export function categorySlug(category: string): string {
  return category.toLowerCase().replace(/[^a-z0-9]/g, "");
}

export const KNOWN_CATEGORIES = [
  "CorpFin",
  "SCS III",
  "APES",
  "E4E",
  "Baseball",
  "Recruiting",
  "Projects",
  "Life",
] as const;
