// The farmer's field area, entered once in the profile and offered to every
// card that asks for it - "kaç dönüm" should not be asked twice.
//
// It fills the CARDS only and is deliberately not in the profile turn the
// model sees: the model is never to do arithmetic, and an area in every
// conversation invites "20 dönüm için 400 kg" from it. The cards hand the
// area to src/budget.py and src/dose_answer.py, where the arithmetic lives.

// The same ids both cards' area fields use on the wire (src/budget.py FIELDS,
// src/dose_answer.py AREA_UNITS), so a stored unit selects the right chip.
export type AreaUnit = "donum" | "hektar";

export const AREA_UNITS: { id: AreaUnit; label: string }[] = [
  { id: "donum", label: "dönüm" },
  { id: "hektar", label: "hektar" },
];

export interface ProfileArea {
  value: string;
  unit: AreaUnit;
}

export const FROM_PROFILE_NOTE = "Profilinizden alındı.";
export const AREA_ERROR = "Tarla alanını sayı olarak yazın (örn. 20 ya da 2,5).";

/** A positive number, with a comma or a point - what the server's
 *  coerce_number accepts. Checked at save time so a typo is caught where it
 *  was typed, not later inside a card. */
export function isValidArea(value: string): boolean {
  const v = value.trim();
  return /^\d+([.,]\d+)?$/.test(v) && Number(v.replace(",", ".")) > 0;
}

/** The profile's area, or null when there is none or the card does not offer
 *  its unit - a value under the wrong chip would be wrong by a factor of ten. */
export function areaForCard(
  area: ProfileArea | null | undefined,
  units: { id: string }[],
): ProfileArea | null {
  if (!area || !units.some((u) => u.id === area.unit)) return null;
  return area;
}
