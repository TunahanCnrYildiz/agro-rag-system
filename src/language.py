"""The language a message is written in, named for the model.

Dependency-free, and scoped to the languages the product is sold in (Hüseyin's
PDF, p10): Turkish, English, Arabic, Russian, Uzbek, French, Spanish, German,
Persian, Azerbaijani, Kazakh, Ukrainian.

WHY IT NAMES THE LANGUAGE AT ALL. Measured 2026-10-29 on the local model: an
Uzbek question answered in Azerbaijani 5 times in 6 while the hint said
"English" (the old detector knew only Turkish and English), and still 3 times
in 5 with no language named - but 5 in 5 in Uzbek once the hint said "Uzbek".
A Turkic neighbour pulls an unnamed Uzbek answer towards itself.

WHY IT RETURNS None WHEN UNSURE. A wrong name is worse than none: None makes
build_language_instruction fall back to "detect the language yourself", which
the model mostly gets right; a wrong name tells it the opposite.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# Turkish (unchanged from the original detector - including the diacritic-free
# forms people type on phones without a Turkish keyboard)
# --------------------------------------------------------------------------- #
_TURKISH_HINT = re.compile(r"[çÇğĞıİöÖşŞüÜ]")
_TURKISH_ONLY = re.compile(r"[ğĞıİşŞ]")

# Function words unlikely to collide with common English words (excludes
# e.g. "her", "kim", "once", "mi" which are also everyday English tokens/names).
_TURKISH_STOPWORDS = {
    "bir", "ve", "bu", "su", "cok", "gibi", "icin", "için", "ile", "ama",
    "fakat", "ancak", "veya", "degil", "değil", "var", "yok",
    "nasil", "nasıl", "neden", "nicin", "niçin", "nerede",
    "iyi", "kotu", "kötü", "buyuk", "büyük", "kucuk", "küçük",
    "sonra", "simdi", "şimdi", "tum", "tüm", "kendi", "benim", "senin",
    "lutfen", "lütfen", "merhaba", "selam", "tesekkur", "teşekkür",
    "evet", "hayir", "hayır", "mumkun", "mümkün", "gerek", "lazim", "lazım",
}

# Agriculture/botany word stems, matched as token prefixes so suffixed forms
# (yapraklarim, topragim, sarariyor, ...) are caught even without diacritics.
_TURKISH_STEMS = (
    "yapra", "topra", "gubre", "gübre", "bitki", "sarar", "sari", "sarı",
    "besin", "domates", "cice", "çiçe", "tohum", "hastal", "zararl", "sera",
    "meyve", "sebze", "urun", "ürün", "hasat", "ekim", "sulama", "mahsul",
    "verim",
)

# --------------------------------------------------------------------------- #
# The other eleven
# --------------------------------------------------------------------------- #
_KAZAKH = set("әғқңөұүһ")      # never in Russian or Ukrainian
_UKRAINIAN = set("їєґі")        # і is also Kazakh - Kazakh is decided first
_PERSIAN = set("پچژگ")          # not in the Arabic alphabet
_PERSIAN_WORDS = re.compile(r"(?<!\S)(?:است|را|می|برای|این|های|که)(?!\S)")
_ARABIC_WORDS = re.compile(r"(?<!\S)(?:ال\S+|في|من|على|إلى|التي|الذي|هذا|ماذا|متى)(?!\S)")

# Uzbek Latin: oʻ/gʻ (with any apostrophe) before a letter, and q not followed
# by u - Turkish has no q at all, and English, French and Spanish write it as qu.
# An English possessive ("dog's") is not oʻ/gʻ, and "Iraq"/"FAQ" are kept out
# by the guard in detect_language: Uzbek wins only when no Latin language has
# real evidence of its own.
_UZBEK_MARK = re.compile(r"[og][ʻ'’‘](?!s\b)[^\W\d_]|q(?!u)")
_UZBEK_WORDS = {"va", "bilan", "uchun", "kerak", "qanday", "qachon", "nima",
                "mumkin", "emas", "yoki", "menga", "mening", "qilish", "nega"}

_LATIN_WORDS = {
    "English": {"the", "and", "of", "to", "is", "in", "for", "with", "your", "you",
                "it", "can", "be", "or", "this", "that", "are", "my", "what", "when",
                "should", "which", "how", "do", "does", "i"},
    "French": {"le", "la", "les", "des", "et", "est", "pour", "dans", "une", "du",
               "vous", "votre", "sur", "pas", "qui", "avec", "au", "je", "mon",
               "mes", "ce", "quel", "quelle", "quand", "dois", "comment"},
    "Spanish": {"el", "los", "las", "y", "es", "para", "en", "una", "del", "su",
                "con", "por", "como", "más", "mi", "mis", "qué", "cuándo", "debo",
                "esta", "cómo"},
    "German": {"der", "die", "das", "und", "ist", "nicht", "mit", "für", "ein",
               "eine", "zu", "den", "sie", "von", "im", "auf", "oder", "ich",
               "soll", "sollte", "meinen", "meine", "meines", "meiner", "was",
               "wann", "welchen", "werden", "wie"},
}
_LATIN_LETTERS = {"French": "çèêàùâœ", "Spanish": "ñ¿¡", "German": "ß"}

_TOKEN = re.compile(r"[^\W\d_]+(?:[ʻ'’‘][^\W\d_]+)?")


def _script_share(letters: list[str], lo: str, hi: str) -> float:
    return sum(1 for c in letters if lo <= c <= hi) / len(letters)


def detect_language(text: str) -> str | None:
    """The language `text` is written in, by English name, or None when the
    evidence does not decide it."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return None
    low = text.lower()

    if _script_share(letters, "؀", "ۿ") > 0.5:
        fa = sum(low.count(c) for c in _PERSIAN) + len(_PERSIAN_WORDS.findall(low))
        ar = len(_ARABIC_WORDS.findall(low))
        if fa == ar == 0:
            return None
        return "Persian" if fa > ar * 0.5 else "Arabic"

    if _script_share(letters, "Ѐ", "ӿ") > 0.5:
        if any(c in _KAZAKH for c in low):
            return "Kazakh"
        if any(c in _UKRAINIAN for c in low):
            return "Ukrainian"
        return "Russian"

    if "ə" in low:
        return "Azerbaijani"
    tokens = [t.lower() for t in _TOKEN.findall(text)]
    words = {lang: sum(1 for t in tokens if t in ws) for lang, ws in _LATIN_WORDS.items()}
    other = max(words.values())
    uzbek = len(_UZBEK_MARK.findall(low)) + sum(1 for t in tokens if t in _UZBEK_WORDS)
    # ı ğ ş belong to Turkish alone here (Azerbaijani was decided above by ə);
    # ç ö ü do not - French writes ç, German ö and ü. Even ı ğ ş lose to a
    # sentence plainly in another language, because a catalog name carries
    # them into it: "How much HİGRO BARF should I use?" is English, and an Uzbek
    # answer naming HİGRO is Uzbek.
    strongest = max(other, uzbek)
    if _TURKISH_ONLY.search(text) and not (
            strongest >= 3
            and strongest > sum(1 for t in tokens if t in _TURKISH_STOPWORDS)):
        return "Turkish"
    # Uzbek before diacritic-free Turkish: Uzbek "sariq" (yellow) would match
    # the Turkish stem "sari", and both share "bu"/"bir". Turkish letters in
    # the text (a catalog name) leave it Uzbek only on strong evidence.
    shared_letters = _TURKISH_HINT.search(text) is not None
    if uzbek and other < 2 and (not shared_letters or uzbek >= 3):
        return "Uzbek"
    # Turkish on weaker evidence - ç/ö/ü, or diacritic-free stopwords and stems -
    # only while no other language's own words reach real evidence: Spanish
    # "su" is a Turkish stopword too, and German writes "für".
    if other < 2 and (shared_letters or set(tokens) & _TURKISH_STOPWORDS or any(
            t.startswith(stem) for t in tokens for stem in _TURKISH_STEMS)):
        return "Turkish"

    scores = dict(words)
    for lang, chars in _LATIN_LETTERS.items():
        scores[lang] += 2 * sum(low.count(c) for c in chars)

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    (best, top), (_, second) = ranked[0], ranked[1]
    if top >= 1 and top > second:
        return best
    return None
