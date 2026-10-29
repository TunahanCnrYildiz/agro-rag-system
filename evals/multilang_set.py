"""The languages the product is sold in (Hüseyin's PDF, p10), four questions
each: nutrition, pruning, soil, and one off-scope - whose refusal must come
back in the asker's language too. Score with `python -m evals.run_multilang`.
"""

KINDS = ("nutrition", "pruning", "soil", "off-scope")

QUESTIONS = {
    'Turkish': [
        'Domates yapraklarım sararıyor, ne yapmalıyım?',
        'Elma ağacını ne zaman budamalıyım?',
        'Toprağımın pH değeri çok yüksek, ne yapabilirim?',
        'Bu akşam hangi filmi izlemeliyim?',
    ],
    'English': [
        'My tomato leaves are turning yellow, what should I do?',
        'When should I prune my apple tree?',
        'My soil pH is very high, what can I do?',
        'Which movie should I watch tonight?',
    ],
    'Arabic': [
        'أوراق الطماطم عندي تصفر، ماذا أفعل؟',
        'متى يجب أن أقلم شجرة التفاح؟',
        'درجة حموضة تربتي مرتفعة جدا، ماذا يمكنني أن أفعل؟',
        'أي فيلم يجب أن أشاهد الليلة؟',
    ],
    'Russian': [
        'Листья моих помидоров желтеют, что мне делать?',
        'Когда нужно обрезать яблоню?',
        'У моей почвы очень высокий pH, что можно сделать?',
        'Какой фильм мне посмотреть сегодня вечером?',
    ],
    'Uzbek': [
        "Pomidor barglarim sarg'ayib qolyapti, nima qilishim kerak?",
        'Olma daraxtini qachon butash kerak?',
        "Tuprog'imning pH darajasi juda yuqori, nima qila olaman?",
        "Bugun kechqurun qaysi filmni ko'rishim kerak?",
    ],
    'French': [
        'Les feuilles de mes tomates jaunissent, que dois-je faire ?',
        'Quand dois-je tailler mon pommier ?',
        'Le pH de mon sol est très élevé, que puis-je faire ?',
        'Quel film devrais-je regarder ce soir ?',
    ],
    'Spanish': [
        'Las hojas de mis tomates se están poniendo amarillas, ¿qué debo hacer?',
        '¿Cuándo debo podar mi manzano?',
        'El pH de mi suelo es muy alto, ¿qué puedo hacer?',
        '¿Qué película debería ver esta noche?',
    ],
    'German': [
        'Die Blätter meiner Tomaten werden gelb, was soll ich tun?',
        'Wann sollte ich meinen Apfelbaum schneiden?',
        'Der pH-Wert meines Bodens ist sehr hoch, was kann ich tun?',
        'Welchen Film soll ich heute Abend schauen?',
    ],
    'Persian': [
        'برگ\u200cهای گوجه\u200cفرنگی من زرد می\u200cشوند، چه کار باید بکنم؟',
        'چه زمانی باید درخت سیبم را هرس کنم؟',
        'پی\u200cاچ خاک من خیلی بالاست، چه کاری می\u200cتوانم بکنم؟',
        'امشب کدام فیلم را تماشا کنم؟',
    ],
    'Azerbaijani': [
        'Pomidorumun yarpaqları saralır, nə etməliyəm?',
        'Alma ağacını nə vaxt budamalıyam?',
        'Torpağımın pH dəyəri çox yüksəkdir, nə edə bilərəm?',
        'Bu axşam hansı filmə baxmalıyam?',
    ],
    'Kazakh': [
        'Қызанақтың жапырақтары сарғайып жатыр, не істеуім керек?',
        'Алма ағашын қашан кесу керек?',
        'Топырағымның pH деңгейі өте жоғары, не істей аламын?',
        'Бүгін кешке қандай фильм көруім керек?',
    ],
    'Ukrainian': [
        'Листя моїх помідорів жовтіє, що мені робити?',
        'Коли потрібно обрізати яблуню?',
        'У мого ґрунту дуже високий pH, що я можу зробити?',
        'Який фільм мені подивитися сьогодні ввечері?',
    ],
}
