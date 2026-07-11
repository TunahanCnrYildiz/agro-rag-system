from src.fetch_dergipark import _OFFTOPIC_REC

# Titles that MUST be flagged as off-topic (livestock / animal science).
OFFTOPIC_TITLES = [
    "Estimation of Growth Curves of Awassi Sheep by Isotonic Regression",
    "İvesi Koyunlarının Büyüme Eğrilerinin Tahmin Edilmesi",
    "Süt sığırlarında karkas verimi ve besi performansı",
    "Broyler tavuklarda rasyon etkisi",
    "Arıcılıkta koloni yönetimi",
]

# In-scope titles that MUST NOT be flagged (plant nutrition vocabulary that
# contains dangerous substrings like 'besin', 'besleme', 'etki').
INSCOPE_TITLES = [
    "Bitki besleme ve toprak besin maddeleri dinamiği",
    "Azotlu gübrelemenin bitki büyümesine etkisi",
    "Mikrobiyal metabolizma ve toprak sağlığı",
    "Buğdayda verim ve besin içeriği",
]


def test_offtopic_titles_flagged():
    for title in OFFTOPIC_TITLES:
        assert _OFFTOPIC_REC.search(title), f"should flag: {title}"


def test_inscope_titles_not_flagged():
    for title in INSCOPE_TITLES:
        assert not _OFFTOPIC_REC.search(title), f"should NOT flag: {title}"
