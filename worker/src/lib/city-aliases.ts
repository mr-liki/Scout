// Several Indian job-board location facets/fields still use pre-rename city
// names (e.g. "Bangalore" instead of "Bengaluru", the name modern location
// inputs actually send). Exact/substring matching alone misses these.
const CITY_ALIASES: Record<string, string[]> = {
  bengaluru: ["bangalore"],
  bangalore: ["bengaluru"],
  mumbai: ["bombay"],
  bombay: ["mumbai"],
  kolkata: ["calcutta"],
  calcutta: ["kolkata"],
  chennai: ["madras"],
  madras: ["chennai"],
  gurugram: ["gurgaon"],
  gurgaon: ["gurugram"],
  pune: ["poona"],
  poona: ["pune"],
  kochi: ["cochin"],
  cochin: ["kochi"],
  vadodara: ["baroda"],
  baroda: ["vadodara"],
  mysuru: ["mysore"],
  mysore: ["mysuru"],
};

export function cityVariants(name: string): string[] {
  const lower = name.toLowerCase().trim();
  return [lower, ...(CITY_ALIASES[lower] || [])];
}

// Words that appear in almost every Indian location string ("City, State,
// India") and also as their own generic catch-all facets on some job boards
// (e.g. Shine's "All India" facet). Token-matching on these would make any
// specific-city search falsely match a nationwide/generic entry, so they're
// excluded from comparison rather than treated as place names.
const NON_DISCRIMINATING_TOKENS = new Set(["india", "all", "state", "region", "pan"]);

function tokenize(s: string): string[] {
  // Splits on anything that isn't a letter/digit, so "Bengaluru (Bangalore)"
  // -> ["bengaluru", "bangalore"] and "Bengaluru, Karnataka, India" ->
  // ["bengaluru", "karnataka", "india"] — candidate strings from job boards
  // are often compound ("City (OldName)", "City1, City2") just like the
  // free-text location input is, so both sides need tokenizing, not just one.
  return s
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((t) => t && !NON_DISCRIMINATING_TOKENS.has(t));
}

// True if `location` (free text, possibly "City, State, Country") refers to
// the same place as `candidate` (a city string from a job board, possibly
// itself compound), once known renames are accounted for.
export function locationMatches(location: string, candidate: string): boolean {
  const cand = candidate.trim();
  if (!cand) return false;

  const lowered = location.toLowerCase();
  const candLower = cand.toLowerCase();
  if (lowered.includes(candLower) || candLower.includes(lowered)) return true;

  const locTokens = tokenize(location);
  const candTokens = tokenize(cand);
  return locTokens.some((lt) => {
    const ltVariants = cityVariants(lt);
    return candTokens.some((ct) => ltVariants.includes(ct) || cityVariants(ct).includes(lt));
  });
}
