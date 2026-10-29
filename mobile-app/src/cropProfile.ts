// The crops a farmer grows live in the profile as free text ("domates, biber").
// When they settle on a crop in the chat - a comparison, "nohut ekeceğim" - the
// server OFFERS it (the `crop_offer` event) and the farmer adds it with a tap.
// Nothing is written without that tap: the PDF's data page promises the
// profile is collected with consent (p12), and choosing a crop is theirs.
import { fold } from "./turkish";

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Whether the profile's free text already names this crop - as a whole word,
 *  so "domates ve biber" holds Domates but "domatesler için" does not hold
 *  "Domates" twice over, and Turkish letters fold either way. */
export function hasCrop(crops: string | undefined, crop: string): boolean {
  if (!crops) return false;
  const pattern = new RegExp(`(^|[^a-z])${escapeRegExp(fold(crop))}([^a-z]|$)`);
  return pattern.test(fold(crops));
}

/** The profile's crops with this one appended, in the farmer's own format. */
export function withCrop(crops: string | undefined, crop: string): string {
  const current = (crops ?? "").trim();
  if (hasCrop(current, crop)) return current;
  return current ? `${current}, ${crop}` : crop;
}
