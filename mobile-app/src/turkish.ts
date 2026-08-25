// Turkish lowercasing for search boxes. toLowerCase() alone maps I to i but
// leaves I undotted, and the things users search for here - crop names, product
// names - are overwhelmingly the ones with dotted capitals.
export function fold(text: string): string {
  return text
    .replace(/I/g, "ı")
    .replace(/İ/g, "i")
    .toLowerCase()
    .replace(/[ışğüöç]/g, (c) => ({ ı: "i", ş: "s", ğ: "g", ü: "u", ö: "o", ç: "c" }[c] ?? c));
}
