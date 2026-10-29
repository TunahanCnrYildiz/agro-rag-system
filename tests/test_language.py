"""src/language.py on text whose language is known.

The questions are evals/multilang_set.py - the set the 2026-10-29
measurement asked, four per language; the paragraphs are
answer-length text in each, written for this test. Every one must come back
with its own name - an unsure detector may say None, a wrong one may not.
"""
import pytest

from src.engine import build_language_instruction
from src.config import SYSTEM_PROMPT
from src.language import detect_language
from evals.multilang_set import QUESTIONS

PARAGRAPHS = [
    ('Yaprak sararması genellikle azot eksikliği, aşırı sulama veya kök sorunlarından kaynaklanabilir. Toprağınızı kontrol edin ve dengeli bir gübreleme programı uygulayın. Organik madde eklemek de toprağın yapısını iyileştirir ve bitkinin besin almasını kolaylaştırır.',
     'Turkish'),
    ('Leaf yellowing is often caused by nitrogen deficiency, overwatering or root problems. Check your soil and apply a balanced fertilization program. Adding organic matter also improves the soil structure and makes it easier for the plant to take up nutrients.',
     'English'),
    ('غالبا ما يكون اصفرار الأوراق ناتجا عن نقص النيتروجين أو الإفراط في الري أو مشاكل في الجذور. افحص التربة وطبق برنامج تسميد متوازن. كما أن إضافة المادة العضوية تحسن بنية التربة وتسهل على النبات امتصاص العناصر الغذائية.',
     'Arabic'),
    ('Пожелтение листьев часто вызвано недостатком азота, избыточным поливом или проблемами с корнями. Проверьте почву и примените сбалансированную программу удобрения. Добавление органического вещества также улучшает структуру почвы и облегчает растению усвоение питательных веществ.',
     'Russian'),
    ("Barglarning sarg'ayishi ko'pincha azot yetishmasligi, ortiqcha sug'orish yoki ildiz muammolari bilan bog'liq bo'ladi. Tuprog'ingizni tekshiring va muvozanatli o'g'itlash dasturini qo'llang. Organik modda qo'shish ham tuproq tuzilishini yaxshilaydi va o'simlikka ozuqa olishni osonlashtiradi.",
     'Uzbek'),
    ("Le jaunissement des feuilles est souvent dû à une carence en azote, à un arrosage excessif ou à des problèmes de racines. Vérifiez votre sol et appliquez un programme de fertilisation équilibré. L'ajout de matière organique améliore aussi la structure du sol.",
     'French'),
    ('El amarilleo de las hojas suele deberse a una deficiencia de nitrógeno, a un riego excesivo o a problemas en las raíces. Revise su suelo y aplique un programa de fertilización equilibrado. Añadir materia orgánica también mejora la estructura del suelo.',
     'Spanish'),
    ('Die Gelbfärbung der Blätter wird oft durch Stickstoffmangel, zu viel Wasser oder Wurzelprobleme verursacht. Prüfen Sie Ihren Boden und wenden Sie ein ausgewogenes Düngeprogramm an. Die Zugabe von organischer Substanz verbessert auch die Bodenstruktur.',
     'German'),
    ('زرد شدن برگ\u200cها اغلب به دلیل کمبود نیتروژن، آبیاری بیش از حد یا مشکلات ریشه است. خاک خود را بررسی کنید و یک برنامه کوددهی متعادل را اجرا کنید. افزودن مواد آلی نیز ساختار خاک را بهبود می\u200cبخشد و جذب مواد مغذی را برای گیاه آسان\u200cتر می\u200cکند.',
     'Persian'),
    ('Yarpaqların saralması çox vaxt azot çatışmazlığı, həddindən artıq suvarma və ya kök problemləri ilə əlaqədardır. Torpağınızı yoxlayın və balanslı gübrələmə proqramı tətbiq edin. Üzvi maddə əlavə etmək də torpağın quruluşunu yaxşılaşdırır.',
     'Azerbaijani'),
    ('Жапырақтардың сарғаюы көбінесе азот жетіспеушілігінен, шамадан тыс суарудан немесе тамыр проблемаларынан болады. Топырағыңызды тексеріп, теңгерімді тыңайту бағдарламасын қолданыңыз. Органикалық заттарды қосу топырақтың құрылымын жақсартады.',
     'Kazakh'),
    ('Пожовтіння листя часто спричинене нестачею азоту, надмірним поливом або проблемами з корінням. Перевірте ґрунт і застосуйте збалансовану програму удобрення. Додавання органічної речовини також покращує структуру ґрунту і полегшує рослині засвоєння поживних речовин.',
     'Ukrainian'),
]

KNOWN = PARAGRAPHS + [(q, lang) for lang, qs in QUESTIONS.items() for q in qs]


@pytest.mark.parametrize("text, language", KNOWN)
def test_known_text_is_named_correctly(text, language):
    assert detect_language(text) == language


def test_every_sold_language_is_covered():
    assert {lang for _, lang in KNOWN} == {
        "Turkish", "English", "Arabic", "Russian", "Uzbek", "French", "Spanish",
        "German", "Persian", "Azerbaijani", "Kazakh", "Ukrainian"}


@pytest.mark.parametrize("text, language", [
    # Turkish typed without a Turkish keyboard is still Turkish.
    ("bir gubre onerisi lazim", "Turkish"),
    ("domates yapraklarim sarariyor", "Turkish"),
    # Uzbek "sariq" (yellow) carries the Turkish stem "sari"; q decides.
    ("Barglar sariq bo'lib qoldi", "Uzbek"),
    # German and French write ü/ö/ç too - their own words decide.
    ("Was ist der beste Dünger für meine Tomaten?", "German"),
    ("Comment améliorer la structure du sol de mon jardin ?", "French"),
    # An English possessive is not Uzbek oʻ/gʻ, and "Iraq" is not Uzbek q.
    ("How do I keep my dog's food away from the garden?", "English"),
    ("What grows well in Iraq during the summer?", "English"),
    # A catalog name carries İ into an English question; the sentence decides.
    ("How much HİGRO BARF should I use per acre?", "English"),
    # ...and into an Uzbek one.
    ("HİGRO BARF o'g'itini pomidorga qanday qo'llash kerak?", "Uzbek"),
    # Spanish "su" is also a Turkish stopword.
    ("Revise su suelo y aplique un programa de fertilización.", "Spanish"),
])
def test_the_traps_between_neighbours(text, language):
    assert detect_language(text) == language


@pytest.mark.parametrize("text", ["", "12345 ?!", "NPK 20-20-20", "pH 7.5"])
def test_no_evidence_names_no_language(text):
    """A wrong name is worse than none: None falls back to the instruction
    that has the model detect the language itself."""
    assert detect_language(text) is None


def test_none_falls_back_to_letting_the_model_detect():
    assert "Automatically detect" in build_language_instruction(None)


def test_the_refusal_example_is_not_turkish_only():
    """Measured 2026-10-29: with only a Turkish example sentence, an English
    off-scope question was refused in Turkish 4 times in 6 - the example
    copied word for word. Rewritten: 5 in 5 English, Turkish control 5 in 5."""
    assert "bu alan disindaki sorulara yanit veremem" not in SYSTEM_PROMPT
    assert "Turkish only when they wrote" in SYSTEM_PROMPT
