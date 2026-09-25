# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Greetings and everyday phrases for World Trip, in the languages of the places
it flies to. Plain data plus a few helpers; no wx, no network.

Every language has:
  * greetings: "hello", "morning", "afternoon" and "evening" (and, where the
    language says late afternoon differently, "afternoon_late"). A language
    without a word for one of them uses its plain hello, and says so with
    `means`, so the translation read to the user is right.
  * "welcome": "Welcome to {city}!" with the city's name in that language, and
    "welcome_plain", "Welcome!", for a city whose name we don't know in it.
  * phrases: PHRASE_KEYS, eight everyday phrases.
Each is P(native text, transliteration, means): the transliteration only for
languages not written in Latin letters (romaji, pinyin with tone marks,
Revised Romanization, Jyutping, RTGS-style Thai, simple Arabic and Persian),
`means` a MEANINGS key or {"id", "en"} when the phrase means something else
than its key. Where the speaker's gender changes the phrase (Thai particles,
Portuguese "obrigado/obrigada"), the entry is G(male, female): the voice
saying it decides.

Meanings are in Indonesian and English, the two languages Hariku speaks.
Which language a place speaks: language_for(country, names, region).
"""

import unicodedata

GREETING_KEYS = ("hello", "morning", "afternoon", "evening")
PHRASE_KEYS = ("thanks", "excuse_me", "how_much", "delicious", "toilet", "nice_to_meet",
               "goodbye", "cheers")
USER_LANGUAGES = ("id", "en")

# What each greeting and phrase means, in the user's language. "{city}" is the
# city's name as the user knows it.
MEANINGS = {
    "hello": {"id": "Halo!", "en": "Hello!"},
    "morning": {"id": "Selamat pagi!", "en": "Good morning!"},
    "afternoon": {"id": "Selamat siang!", "en": "Good afternoon!"},
    "afternoon_late": {"id": "Selamat sore!", "en": "Good afternoon!"},
    "evening": {"id": "Selamat malam!", "en": "Good evening!"},
    "how_are_you": {"id": "Apa kabar?", "en": "How are you?"},
    "welcome": {"id": "Selamat datang di {city}!", "en": "Welcome to {city}!"},
    "welcome_plain": {"id": "Selamat datang!", "en": "Welcome!"},
    "thanks": {"id": "Terima kasih.", "en": "Thank you."},
    "thanks_a_lot": {"id": "Terima kasih banyak.", "en": "Thank you very much."},
    "excuse_me": {"id": "Permisi.", "en": "Excuse me."},
    "how_much": {"id": "Ini berapa harganya?", "en": "How much is this?"},
    "delicious": {"id": "Enak sekali!", "en": "Delicious!"},
    "toilet": {"id": "Toiletnya di mana?", "en": "Where is the toilet?"},
    "nice_to_meet": {"id": "Senang berkenalan denganmu.", "en": "Nice to meet you."},
    "goodbye": {"id": "Sampai jumpa.", "en": "Goodbye."},
    "see_you": {"id": "Sampai jumpa lagi.", "en": "See you again."},
    "cheers": {"id": "Bersulang!", "en": "Cheers!"},
    "to_your_health": {"id": "Untuk kesehatanmu!", "en": "To your health!"},
}


def P(native, translit="", means=None):
    """One greeting or phrase: its text, its transliteration (for languages
    not written in Latin letters) and what it means, when not its own key."""
    return {"native": native, "translit": translit, "means": means}


def G(male, female):
    """A phrase that depends on who says it: P() for a man and for a woman."""
    return {"male": male, "female": female}


# ------------------------------------------------------------
# The languages
# ------------------------------------------------------------

LANGUAGES = {
    "ja": {
        "name": {"id": "Jepang", "en": "Japanese"},
        "latin": False,
        "voices": ("ja-JP",),
        "greetings": {
            "hello": P("こんにちは！", "Konnichiwa!"),
            "morning": P("おはようございます！", "Ohayō gozaimasu!"),
            "afternoon": P("こんにちは！", "Konnichiwa!"),
            "evening": P("こんばんは！", "Konbanwa!"),
        },
        "welcome": P("{city}へようこそ！", "{city} e yōkoso!"),
        "welcome_plain": P("ようこそ！", "Yōkoso!"),
        "phrases": {
            "thanks": P("ありがとうございます。", "Arigatō gozaimasu."),
            "excuse_me": P("すみません。", "Sumimasen."),
            "how_much": P("これはいくらですか？", "Kore wa ikura desu ka?"),
            "delicious": P("おいしいです！", "Oishii desu!"),
            "toilet": P("トイレはどこですか？", "Toire wa doko desu ka?"),
            "nice_to_meet": P("はじめまして。", "Hajimemashite."),
            "goodbye": P("さようなら。", "Sayōnara."),
            "cheers": P("乾杯！", "Kanpai!"),
        },
    },
    "ko": {
        "name": {"id": "Korea", "en": "Korean"},
        "latin": False,
        "voices": ("ko-KR",),
        "greetings": {
            "hello": P("안녕하세요!", "Annyeonghaseyo!"),
            "morning": P("안녕하세요!", "Annyeonghaseyo!", "hello"),
            "afternoon": P("안녕하세요!", "Annyeonghaseyo!", "hello"),
            "evening": P("안녕하세요!", "Annyeonghaseyo!", "hello"),
        },
        "welcome": P("{city}에 오신 것을 환영합니다!", "{city}-e osin geoseul hwanyeonghamnida!"),
        "welcome_plain": P("환영합니다!", "Hwanyeonghamnida!"),
        "phrases": {
            "thanks": P("감사합니다.", "Gamsahamnida."),
            "excuse_me": P("실례합니다.", "Sillyehamnida."),
            "how_much": P("이거 얼마예요?", "Igeo eolmayeyo?"),
            "delicious": P("맛있어요!", "Masisseoyo!"),
            "toilet": P("화장실이 어디예요?", "Hwajangsiri eodiyeyo?"),
            "nice_to_meet": P("만나서 반갑습니다.", "Mannaseo bangapseumnida."),
            "goodbye": P("안녕히 계세요.", "Annyeonghi gyeseyo."),
            "cheers": P("건배!", "Geonbae!"),
        },
    },
    "zh": {
        "name": {"id": "Mandarin", "en": "Mandarin Chinese"},
        "latin": False,
        # Not "zh" alone: zh-HK voices speak Cantonese.
        "voices": ("zh-CN", "zh-SG", "zh-TW", "cmn-CN"),
        "any_region": False,
        "greetings": {
            "hello": P("你好！", "Nǐ hǎo!"),
            "morning": P("早上好！", "Zǎoshang hǎo!"),
            "afternoon": P("下午好！", "Xiàwǔ hǎo!"),
            "evening": P("晚上好！", "Wǎnshang hǎo!"),
        },
        "welcome": P("欢迎来到{city}！", "Huānyíng láidào {city}!"),
        "welcome_plain": P("欢迎！", "Huānyíng!"),
        "phrases": {
            "thanks": P("谢谢。", "Xièxie."),
            "excuse_me": P("不好意思。", "Bù hǎoyìsi."),
            "how_much": P("这个多少钱？", "Zhège duōshao qián?"),
            "delicious": P("真好吃！", "Zhēn hǎochī!"),
            "toilet": P("洗手间在哪里？", "Xǐshǒujiān zài nǎlǐ?"),
            "nice_to_meet": P("很高兴认识你。", "Hěn gāoxìng rènshi nǐ."),
            "goodbye": P("再见！", "Zàijiàn!"),
            "cheers": P("干杯！", "Gānbēi!"),
        },
    },
    "zh-TW": {
        "name": {"id": "Mandarin Taiwan", "en": "Taiwanese Mandarin"},
        "latin": False,
        "voices": ("zh-TW", "zh-CN"),
        "any_region": False,
        "greetings": {
            "hello": P("你好！", "Nǐ hǎo!"),
            "morning": P("早安！", "Zǎo ān!"),
            "afternoon": P("午安！", "Wǔ ān!"),
            "evening": P("晚上好！", "Wǎnshang hǎo!"),
        },
        "welcome": P("歡迎來到{city}！", "Huānyíng láidào {city}!"),
        "welcome_plain": P("歡迎！", "Huānyíng!"),
        "phrases": {
            "thanks": P("謝謝。", "Xièxie."),
            "excuse_me": P("不好意思。", "Bù hǎoyìsi."),
            "how_much": P("這個多少錢？", "Zhège duōshǎo qián?"),
            "delicious": P("真好吃！", "Zhēn hǎochī!"),
            "toilet": P("洗手間在哪裡？", "Xǐshǒujiān zài nǎlǐ?"),
            "nice_to_meet": P("很高興認識你。", "Hěn gāoxìng rènshì nǐ."),
            "goodbye": P("再見！", "Zàijiàn!"),
            "cheers": P("乾杯！", "Gānbēi!"),
        },
    },
    "yue": {
        "name": {"id": "Kanton", "en": "Cantonese"},
        "latin": False,
        "voices": ("zh-HK", "yue-HK", "yue-CN", "yue"),
        "greetings": {
            "hello": P("你好！", "Nei5 hou2!"),
            "morning": P("早晨！", "Zou2 san4!"),
            "afternoon": P("你好！", "Nei5 hou2!", "hello"),
            "evening": P("你好！", "Nei5 hou2!", "hello"),
        },
        "welcome": P("歡迎嚟到{city}！", "Fun1 jing4 lai4 dou3 {city}!"),
        "welcome_plain": P("歡迎！", "Fun1 jing4!"),
        "phrases": {
            "thanks": P("唔該。", "M4 goi1.",
                        {"id": "Terima kasih (untuk bantuan atau layanan).",
                         "en": "Thank you (for help or a service)."}),
            "excuse_me": P("唔好意思。", "M4 hou2 ji3 si1."),
            "how_much": P("呢個幾多錢？", "Ni1 go3 gei2 do1 cin2?"),
            "delicious": P("好好食！", "Hou2 hou2 sik6!"),
            "toilet": P("洗手間喺邊度？", "Sai2 sau2 gaan1 hai2 bin1 dou6?"),
            "nice_to_meet": P("好高興識到你。", "Hou2 gou1 hing3 sik1 dou2 nei5."),
            "goodbye": P("再見！", "Zoi3 gin3!"),
            "cheers": P("飲勝！", "Jam2 sing3!"),
        },
    },
    "th": {
        "name": {"id": "Thai", "en": "Thai"},
        "latin": False,
        "voices": ("th-TH",),
        # Polite speech ends with khrap (a man) or kha (a woman).
        "note": {"id": "Laki-laki menutup kalimat sopan dengan khrap, perempuan dengan kha.",
                 "en": "Men end polite sentences with khrap, women with kha."},
        "greetings": {
            "hello": G(P("สวัสดีครับ", "Sawatdi khrap!"), P("สวัสดีค่ะ", "Sawatdi kha!")),
            "morning": G(P("สวัสดีครับ", "Sawatdi khrap!", "hello"),
                         P("สวัสดีค่ะ", "Sawatdi kha!", "hello")),
            "afternoon": G(P("สวัสดีครับ", "Sawatdi khrap!", "hello"),
                           P("สวัสดีค่ะ", "Sawatdi kha!", "hello")),
            "evening": G(P("สวัสดีครับ", "Sawatdi khrap!", "hello"),
                         P("สวัสดีค่ะ", "Sawatdi kha!", "hello")),
        },
        "welcome": P("ยินดีต้อนรับสู่{city}", "Yindi tonrap su {city}!"),
        "welcome_plain": P("ยินดีต้อนรับ", "Yindi tonrap!"),
        "phrases": {
            "thanks": G(P("ขอบคุณครับ", "Khop khun khrap."), P("ขอบคุณค่ะ", "Khop khun kha.")),
            "excuse_me": G(P("ขอโทษครับ", "Kho thot khrap."), P("ขอโทษค่ะ", "Kho thot kha.")),
            "how_much": G(P("อันนี้เท่าไหร่ครับ", "An ni thao rai khrap?"),
                          P("อันนี้เท่าไหร่คะ", "An ni thao rai kha?")),
            "delicious": G(P("อร่อยมากครับ", "Aroi mak khrap!"), P("อร่อยมากค่ะ", "Aroi mak kha!")),
            "toilet": G(P("ห้องน้ำอยู่ที่ไหนครับ", "Hong nam yu thi nai khrap?"),
                        P("ห้องน้ำอยู่ที่ไหนคะ", "Hong nam yu thi nai kha?")),
            "nice_to_meet": G(P("ยินดีที่ได้รู้จักครับ", "Yindi thi dai ruchak khrap."),
                              P("ยินดีที่ได้รู้จักค่ะ", "Yindi thi dai ruchak kha.")),
            "goodbye": G(P("แล้วพบกันใหม่ครับ", "Laeo phop kan mai khrap.", "see_you"),
                         P("แล้วพบกันใหม่ค่ะ", "Laeo phop kan mai kha.", "see_you")),
            "cheers": P("ชนแก้ว!", "Chon kaeo!"),
        },
    },
    "vi": {
        "name": {"id": "Vietnam", "en": "Vietnamese"},
        "latin": True,
        "voices": ("vi-VN",),
        "greetings": {
            "hello": P("Xin chào!"),
            "morning": P("Chào buổi sáng!"),
            "afternoon": P("Chào buổi chiều!"),
            "evening": P("Chào buổi tối!"),
        },
        "welcome": P("Chào mừng bạn đến với {city}!"),
        "welcome_plain": P("Chào mừng bạn!"),
        "phrases": {
            "thanks": P("Cảm ơn bạn!"),
            "excuse_me": P("Xin lỗi."),
            "how_much": P("Cái này bao nhiêu tiền?"),
            "delicious": P("Ngon quá!"),
            "toilet": P("Nhà vệ sinh ở đâu?"),
            "nice_to_meet": P("Rất vui được gặp bạn."),
            "goodbye": P("Tạm biệt!"),
            "cheers": P("Một, hai, ba, dô!", "",
                        {"id": "Satu, dua, tiga, bersulang!", "en": "One, two, three, cheers!"}),
        },
    },
    "ms": {
        "name": {"id": "Melayu", "en": "Malay"},
        "latin": True,
        "voices": ("ms-MY",),
        "greetings": {
            "hello": P("Apa khabar?", "", "how_are_you"),
            "morning": P("Selamat pagi!"),
            "afternoon": P("Selamat tengah hari!"),
            "afternoon_late": P("Selamat petang!"),
            "evening": P("Selamat malam!"),
        },
        "welcome": P("Selamat datang ke {city}!"),
        "welcome_plain": P("Selamat datang!"),
        "phrases": {
            "thanks": P("Terima kasih."),
            "excuse_me": P("Tumpang tanya.", "",
                           {"id": "Numpang tanya.", "en": "Excuse me, may I ask something?"}),
            "how_much": P("Berapa harga ini?"),
            "delicious": P("Sedapnya!"),
            "toilet": P("Tandas di mana?"),
            "nice_to_meet": P("Gembira berkenalan dengan anda."),
            "goodbye": P("Selamat tinggal."),
            "cheers": P("Yam seng!"),
        },
    },
    "tl": {
        "name": {"id": "Tagalog", "en": "Tagalog"},
        "latin": True,
        "voices": ("fil-PH", "tl-PH", "fil", "tl"),
        "greetings": {
            "hello": P("Kumusta!", "", "how_are_you"),
            "morning": P("Magandang umaga!"),
            "afternoon": P("Magandang hapon!"),
            "evening": P("Magandang gabi!"),
        },
        "welcome": P("Maligayang pagdating sa {city}!"),
        "welcome_plain": P("Maligayang pagdating!"),
        "phrases": {
            "thanks": P("Salamat po."),
            "excuse_me": P("Mawalang-galang na po."),
            "how_much": P("Magkano po ito?"),
            "delicious": P("Ang sarap!"),
            "toilet": P("Nasaan po ang banyo?"),
            "nice_to_meet": P("Ikinagagalak ko pong makilala kayo."),
            "goodbye": P("Paalam po."),
            "cheers": P("Tagay!"),
        },
    },
    "hi": {
        "name": {"id": "Hindi", "en": "Hindi"},
        "latin": False,
        "voices": ("hi-IN",),
        "greetings": {
            "hello": P("नमस्ते!", "Namaste!"),
            "morning": P("सुप्रभात!", "Suprabhat!"),
            "afternoon": P("नमस्ते!", "Namaste!", "hello"),
            "evening": P("शुभ संध्या!", "Shubh sandhya!"),
        },
        "welcome": P("{city} में आपका स्वागत है!", "{city} mein aapka swagat hai!"),
        "welcome_plain": P("आपका स्वागत है!", "Aapka swagat hai!"),
        "phrases": {
            "thanks": P("धन्यवाद।", "Dhanyavaad."),
            "excuse_me": P("माफ़ कीजिए।", "Maaf kijiye."),
            "how_much": P("यह कितने का है?", "Yeh kitne ka hai?"),
            "delicious": P("बहुत स्वादिष्ट है!", "Bahut swaadisht hai!"),
            "toilet": P("शौचालय कहाँ है?", "Shauchalay kahaan hai?"),
            "nice_to_meet": P("आपसे मिलकर खुशी हुई।", "Aapse milkar khushi hui."),
            "goodbye": P("फिर मिलेंगे।", "Phir milenge.", "see_you"),
            "cheers": P("आपकी सेहत के लिए!", "Aapki sehat ke liye!", "to_your_health"),
        },
    },
    "ar": {
        "name": {"id": "Arab", "en": "Arabic"},
        "latin": False,
        "voices": ("ar-SA", "ar-EG", "ar-AE", "ar-JO", "ar-MA", "ar"),
        "greetings": {
            "hello": P("مرحباً!", "Marhaban!"),
            "morning": P("صباح الخير!", "Sabah al-khair!"),
            "afternoon": P("مساء الخير!", "Masa al-khair!"),
            "evening": P("مساء الخير!", "Masa al-khair!"),
        },
        "welcome": P("أهلاً وسهلاً في {city}!", "Ahlan wa sahlan fi {city}!"),
        "welcome_plain": P("أهلاً وسهلاً!", "Ahlan wa sahlan!"),
        "phrases": {
            "thanks": P("شكراً.", "Shukran."),
            "excuse_me": P("لو سمحت.", "Law samaht."),
            "how_much": P("بكم هذا؟", "Bikam hadha?"),
            "delicious": P("لذيذ جداً!", "Ladhidh jiddan!"),
            "toilet": P("أين الحمّام؟", "Ayna al-hammam?"),
            "nice_to_meet": P("تشرفنا.", "Tasharrafna."),
            "goodbye": P("مع السلامة.", "Ma'a as-salama."),
            "cheers": P("في صحتك!", "Fi sihhatak!", "to_your_health"),
        },
    },
    "tr": {
        "name": {"id": "Turki", "en": "Turkish"},
        "latin": True,
        "voices": ("tr-TR",),
        "greetings": {
            "hello": P("Merhaba!"),
            "morning": P("Günaydın!"),
            "afternoon": P("İyi günler!"),
            "evening": P("İyi akşamlar!"),
        },
        # "{city_to}" is the city with the dative suffix: İstanbul'a, Ankara'ya.
        "welcome": P("{city_to} hoş geldiniz!"),
        "welcome_plain": P("Hoş geldiniz!"),
        "phrases": {
            "thanks": P("Teşekkür ederim."),
            "excuse_me": P("Affedersiniz."),
            "how_much": P("Bu ne kadar?"),
            "delicious": P("Çok lezzetli!"),
            "toilet": P("Tuvalet nerede?"),
            "nice_to_meet": P("Tanıştığıma memnun oldum."),
            "goodbye": P("Hoşça kalın!"),
            "cheers": P("Şerefe!"),
        },
    },
    "ru": {
        "name": {"id": "Rusia", "en": "Russian"},
        "latin": False,
        "voices": ("ru-RU",),
        "greetings": {
            "hello": P("Здравствуйте!", "Zdravstvuyte!"),
            "morning": P("Доброе утро!", "Dobroye utro!"),
            "afternoon": P("Добрый день!", "Dobry den!"),
            "evening": P("Добрый вечер!", "Dobry vecher!"),
        },
        # "{city_to}": the accusative after "в" (Москва -> в Москву).
        "welcome": P("Добро пожаловать в {city_to}!", "Dobro pozhalovat v {city_to}!"),
        "welcome_plain": P("Добро пожаловать!", "Dobro pozhalovat!"),
        "phrases": {
            "thanks": P("Спасибо!", "Spasibo!"),
            "excuse_me": P("Извините.", "Izvinite."),
            "how_much": P("Сколько это стоит?", "Skolko eto stoit?"),
            "delicious": P("Очень вкусно!", "Ochen vkusno!"),
            "toilet": P("Где туалет?", "Gde tualet?"),
            "nice_to_meet": P("Очень приятно.", "Ochen priyatno."),
            "goodbye": P("До свидания!", "Do svidaniya!"),
            "cheers": P("За здоровье!", "Za zdorovye!", "to_your_health"),
        },
    },
    "uk": {
        "name": {"id": "Ukraina", "en": "Ukrainian"},
        "latin": False,
        "voices": ("uk-UA",),
        # Ukrainian changes the city's ending after "до": known cities only.
        "welcome_forms_only": True,
        "greetings": {
            "hello": P("Вітаю!", "Vitaiu!"),
            "morning": P("Доброго ранку!", "Dobroho ranku!"),
            "afternoon": P("Добрий день!", "Dobryi den!"),
            "evening": P("Добрий вечір!", "Dobryi vechir!"),
        },
        "welcome": P("Ласкаво просимо до {city}!", "Laskavo prosymo do {city}!"),
        "welcome_plain": P("Ласкаво просимо!", "Laskavo prosymo!"),
        "phrases": {
            "thanks": P("Дякую!", "Diakuiu!"),
            "excuse_me": P("Вибачте.", "Vybachte."),
            "how_much": P("Скільки це коштує?", "Skilky tse koshtuie?"),
            "delicious": P("Дуже смачно!", "Duzhe smachno!"),
            "toilet": P("Де туалет?", "De tualet?"),
            "nice_to_meet": P("Приємно познайомитися.", "Pryiemno poznaiomytysia."),
            "goodbye": P("До побачення!", "Do pobachennia!"),
            "cheers": P("Будьмо!", "Budmo!"),
        },
    },
    "fr": {
        "name": {"id": "Prancis", "en": "French"},
        "latin": True,
        "voices": ("fr-FR", "fr-CA", "fr-BE", "fr-CH"),
        "greetings": {
            "hello": P("Bonjour !"),
            "morning": P("Bonjour !", "", "hello"),
            "afternoon": P("Bonjour !", "", "hello"),
            "evening": P("Bonsoir !"),
        },
        "welcome": P("Bienvenue à {city} !"),
        "welcome_plain": P("Bienvenue !"),
        "phrases": {
            "thanks": P("Merci beaucoup !", "", "thanks_a_lot"),
            "excuse_me": P("Excusez-moi."),
            "how_much": P("C'est combien ?"),
            "delicious": P("C'est délicieux !"),
            "toilet": P("Où sont les toilettes ?"),
            "nice_to_meet": P("Enchanté !"),
            "goodbye": P("Au revoir !"),
            "cheers": P("Santé !"),
        },
    },
    "de": {
        "name": {"id": "Jerman", "en": "German"},
        "latin": True,
        "voices": ("de-DE", "de-AT", "de-CH"),
        "greetings": {
            "hello": P("Hallo!"),
            "morning": P("Guten Morgen!"),
            "afternoon": P("Guten Tag!"),
            "evening": P("Guten Abend!"),
        },
        "welcome": P("Willkommen in {city}!"),
        "welcome_plain": P("Willkommen!"),
        "phrases": {
            "thanks": P("Danke schön!"),
            "excuse_me": P("Entschuldigung."),
            "how_much": P("Was kostet das?"),
            "delicious": P("Sehr lecker!"),
            "toilet": P("Wo ist die Toilette?"),
            "nice_to_meet": P("Freut mich!"),
            "goodbye": P("Auf Wiedersehen!"),
            "cheers": P("Prost!"),
        },
    },
    "es": {
        "name": {"id": "Spanyol", "en": "Spanish"},
        "latin": True,
        "voices": ("es-ES", "es-MX", "es-US"),
        "greetings": {
            "hello": P("¡Hola!"),
            "morning": P("¡Buenos días!"),
            "afternoon": P("¡Buenas tardes!"),
            "evening": P("¡Buenas noches!"),
        },
        "welcome": P("¡Bienvenidos a {city}!"),
        "welcome_plain": P("¡Bienvenidos!"),
        "phrases": {
            "thanks": P("¡Muchas gracias!", "", "thanks_a_lot"),
            "excuse_me": P("Disculpe."),
            "how_much": P("¿Cuánto cuesta esto?"),
            "delicious": P("¡Está delicioso!"),
            "toilet": P("¿Dónde está el baño?"),
            "nice_to_meet": P("Mucho gusto."),
            "goodbye": P("¡Adiós!"),
            "cheers": P("¡Salud!"),
        },
    },
    "pt": {
        "name": {"id": "Portugis (Brasil)", "en": "Brazilian Portuguese"},
        "latin": True,
        "voices": ("pt-BR", "pt-PT"),
        "greetings": {
            "hello": P("Olá!"),
            "morning": P("Bom dia!"),
            "afternoon": P("Boa tarde!"),
            "evening": P("Boa noite!"),
        },
        # "{city_to}": "a Lisboa", but "ao Rio de Janeiro".
        "welcome": P("Bem-vindos {city_to}!"),
        "welcome_plain": P("Bem-vindos!"),
        "phrases": {
            "thanks": G(P("Obrigado!"), P("Obrigada!")),
            "excuse_me": P("Com licença."),
            "how_much": P("Quanto custa isto?"),
            "delicious": P("Que delícia!"),
            "toilet": P("Onde fica o banheiro?"),
            "nice_to_meet": P("Muito prazer!"),
            "goodbye": P("Até logo!", "", "see_you"),
            "cheers": P("Saúde!"),
        },
    },
    "it": {
        "name": {"id": "Italia", "en": "Italian"},
        "latin": True,
        "voices": ("it-IT",),
        "greetings": {
            "hello": P("Ciao!"),
            "morning": P("Buongiorno!"),
            "afternoon": P("Buon pomeriggio!"),
            "evening": P("Buonasera!"),
        },
        "welcome": P("Benvenuti a {city}!"),
        "welcome_plain": P("Benvenuti!"),
        "phrases": {
            "thanks": P("Grazie mille!", "", "thanks_a_lot"),
            "excuse_me": P("Mi scusi."),
            "how_much": P("Quanto costa questo?"),
            "delicious": P("Buonissimo!"),
            "toilet": P("Dov'è il bagno?"),
            "nice_to_meet": P("Molto piacere!"),
            "goodbye": P("Arrivederci!"),
            "cheers": P("Cin cin!"),
        },
    },
    "nl": {
        "name": {"id": "Belanda", "en": "Dutch"},
        "latin": True,
        "voices": ("nl-NL", "nl-BE"),
        "greetings": {
            "hello": P("Hallo!"),
            "morning": P("Goedemorgen!"),
            "afternoon": P("Goedemiddag!"),
            "evening": P("Goedenavond!"),
        },
        "welcome": P("Welkom in {city}!"),
        "welcome_plain": P("Welkom!"),
        "phrases": {
            "thanks": P("Dank u wel!"),
            "excuse_me": P("Pardon."),
            "how_much": P("Hoeveel kost dit?"),
            "delicious": P("Heel lekker!"),
            "toilet": P("Waar is het toilet?"),
            "nice_to_meet": P("Leuk je te ontmoeten."),
            "goodbye": P("Tot ziens!"),
            "cheers": P("Proost!"),
        },
    },
    "el": {
        "name": {"id": "Yunani", "en": "Greek"},
        "latin": False,
        "voices": ("el-GR",),
        # Greek puts the city after an article (στην Αθήνα, στο Ηράκλειο): known cities only.
        "welcome_forms_only": True,
        "greetings": {
            "hello": P("Γεια σας!", "Yia sas!"),
            "morning": P("Καλημέρα!", "Kaliméra!"),
            "afternoon": P("Γεια σας!", "Yia sas!", "hello"),
            "evening": P("Καλησπέρα!", "Kalispéra!"),
        },
        "welcome": P("Καλώς ήρθατε στην {city}!", "Kalós írthate stin {city}!"),
        "welcome_plain": P("Καλώς ήρθατε!", "Kalós írthate!"),
        "phrases": {
            "thanks": P("Ευχαριστώ!", "Efcharistó!"),
            "excuse_me": P("Συγγνώμη.", "Signómi."),
            "how_much": P("Πόσο κάνει αυτό;", "Póso kánei aftó?"),
            "delicious": P("Πολύ νόστιμο!", "Polý nóstimo!"),
            "toilet": P("Πού είναι η τουαλέτα;", "Pou eínai i toualéta?"),
            "nice_to_meet": P("Χάρηκα πολύ.", "Chárika polý."),
            "goodbye": P("Αντίο!", "Antío!"),
            "cheers": P("Γεια μας!", "Yia mas!"),
        },
    },
    "sv": {
        "name": {"id": "Swedia", "en": "Swedish"},
        "latin": True,
        "voices": ("sv-SE",),
        "greetings": {
            "hello": P("Hej!"),
            "morning": P("God morgon!"),
            "afternoon": P("God eftermiddag!"),
            "evening": P("God kväll!"),
        },
        "welcome": P("Välkommen till {city}!"),
        "welcome_plain": P("Välkommen!"),
        "phrases": {
            "thanks": P("Tack så mycket!", "", "thanks_a_lot"),
            "excuse_me": P("Ursäkta."),
            "how_much": P("Hur mycket kostar det här?"),
            "delicious": P("Jättegott!"),
            "toilet": P("Var är toaletten?"),
            "nice_to_meet": P("Trevligt att träffas."),
            "goodbye": P("Hej då!"),
            "cheers": P("Skål!"),
        },
    },
    "pl": {
        "name": {"id": "Polandia", "en": "Polish"},
        "latin": True,
        "voices": ("pl-PL",),
        # Polish puts the city in the locative (w Warszawie): known cities only.
        "welcome_forms_only": True,
        "greetings": {
            "hello": P("Cześć!"),
            "morning": P("Dzień dobry!"),
            "afternoon": P("Dzień dobry!"),
            "evening": P("Dobry wieczór!"),
        },
        "welcome": P("Witamy w {city}!"),
        "welcome_plain": P("Witamy!"),
        "phrases": {
            "thanks": P("Dziękuję!"),
            "excuse_me": P("Przepraszam."),
            "how_much": P("Ile to kosztuje?"),
            "delicious": P("Pyszne!"),
            "toilet": P("Gdzie jest toaleta?"),
            "nice_to_meet": P("Miło mi."),
            "goodbye": P("Do widzenia!"),
            "cheers": P("Na zdrowie!"),
        },
    },
    "en": {
        "name": {"id": "Inggris", "en": "English"},
        "latin": True,
        "voices": ("en-GB", "en-US", "en-AU"),
        "greetings": {
            "hello": P("Hello!"),
            "morning": P("Good morning!"),
            "afternoon": P("Good afternoon!"),
            "evening": P("Good evening!"),
        },
        "welcome": P("Welcome to {city}!"),
        "welcome_plain": P("Welcome!"),
        "phrases": {
            "thanks": P("Thank you very much!", "", "thanks_a_lot"),
            "excuse_me": P("Excuse me."),
            "how_much": P("How much is this?"),
            "delicious": P("This is delicious!"),
            "toilet": P("Where is the toilet?"),
            "nice_to_meet": P("Nice to meet you!"),
            "goodbye": P("Goodbye!"),
            "cheers": P("Cheers!"),
        },
    },
    "id": {
        "name": {"id": "Indonesia", "en": "Indonesian"},
        "latin": True,
        "voices": ("id-ID",),
        "greetings": {
            "hello": P("Halo!"),
            "morning": P("Selamat pagi!"),
            "afternoon": P("Selamat siang!"),
            "afternoon_late": P("Selamat sore!"),
            "evening": P("Selamat malam!"),
        },
        "welcome": P("Selamat datang di {city}!"),
        "welcome_plain": P("Selamat datang!"),
        "phrases": {
            "thanks": P("Terima kasih!"),
            "excuse_me": P("Permisi."),
            "how_much": P("Ini berapa?"),
            "delicious": P("Enak sekali!"),
            "toilet": P("Toiletnya di mana?"),
            "nice_to_meet": P("Senang berkenalan!"),
            "goodbye": P("Sampai jumpa!"),
            "cheers": P("Bersulang!"),
        },
    },
    "jv": {
        "name": {"id": "Jawa", "en": "Javanese"},
        "latin": True,
        "voices": ("jv-ID",),
        # Polite Javanese (krama), as a guest speaks.
        "greetings": {
            "hello": P("Pripun kabaripun?", "", "how_are_you"),
            "morning": P("Sugeng enjing!"),
            "afternoon": P("Sugeng siang!"),
            "afternoon_late": P("Sugeng sonten!"),
            "evening": P("Sugeng dalu!"),
        },
        "welcome": P("Sugeng rawuh ing {city}!"),
        "welcome_plain": P("Sugeng rawuh!"),
        "phrases": {
            "thanks": P("Matur nuwun."),
            "excuse_me": P("Nuwun sewu."),
            "how_much": P("Niki pinten?"),
            "delicious": P("Eco sanget!"),
            "toilet": P("Kamar mandinipun wonten pundi?",
                        "", {"id": "Kamar mandinya di mana?", "en": "Where is the bathroom?"}),
            "nice_to_meet": P("Seneng saged tepang kaliyan panjenengan."),
            "goodbye": P("Pareng rumiyin.", "",
                         {"id": "Aku pamit dulu.", "en": "I'll take my leave now."}),
            "cheers": P("Sugeng dhahar!", "",
                        {"id": "Selamat makan!", "en": "Enjoy your meal!"}),
        },
    },
    "he": {
        "name": {"id": "Ibrani", "en": "Hebrew"},
        "latin": False,
        "voices": ("he-IL", "iw-IL"),
        "greetings": {
            "hello": P("שלום!", "Shalom!"),
            "morning": P("בוקר טוב!", "Boker tov!"),
            "afternoon": P("צהריים טובים!", "Tzohorayim tovim!"),
            "evening": P("ערב טוב!", "Erev tov!"),
        },
        "welcome": P("ברוכים הבאים ל{city}!", "Bruchim haba'im le-{city}!"),
        "welcome_plain": P("ברוכים הבאים!", "Bruchim haba'im!"),
        "phrases": {
            "thanks": P("תודה רבה!", "Toda raba!", "thanks_a_lot"),
            "excuse_me": P("סליחה.", "Slicha."),
            "how_much": P("כמה זה עולה?", "Kama ze ole?"),
            "delicious": P("טעים מאוד!", "Ta'im me'od!"),
            "toilet": P("איפה השירותים?", "Eifo ha-sherutim?"),
            "nice_to_meet": P("נעים מאוד.", "Na'im me'od."),
            "goodbye": P("להתראות!", "Lehitra'ot!", "see_you"),
            "cheers": P("לחיים!", "Lechaim!"),
        },
    },
    "fa": {
        "name": {"id": "Persia", "en": "Persian"},
        "latin": False,
        "voices": ("fa-IR", "fa-AF", "prs-AF"),
        "greetings": {
            "hello": P("سلام!", "Salam!"),
            "morning": P("صبح بخیر!", "Sobh bekheir!"),
            "afternoon": P("عصر بخیر!", "Asr bekheir!"),
            "evening": P("شب بخیر!", "Shab bekheir!"),
        },
        "welcome": P("به {city} خوش آمدید!", "Be {city} khosh amadid!"),
        "welcome_plain": P("خوش آمدید!", "Khosh amadid!"),
        "phrases": {
            "thanks": P("متشکرم.", "Moteshakkeram."),
            "excuse_me": P("ببخشید.", "Bebakhshid."),
            "how_much": P("این چنده؟", "In chande?"),
            "delicious": P("خیلی خوشمزه است!", "Kheili khoshmaze ast!"),
            "toilet": P("دستشویی کجاست؟", "Dastshuyi kojast?"),
            "nice_to_meet": P("از آشنایی با شما خوشوقتم.", "Az ashnayi ba shoma khoshvaghtam."),
            "goodbye": P("خداحافظ!", "Khodahafez!"),
            "cheers": P("به سلامتی!", "Be salamati!", "to_your_health"),
        },
    },
    "sw": {
        "name": {"id": "Swahili", "en": "Swahili"},
        "latin": True,
        "voices": ("sw-KE", "sw-TZ"),
        "greetings": {
            "hello": P("Hujambo!"),
            "morning": P("Habari za asubuhi!"),
            "afternoon": P("Habari za mchana!"),
            "evening": P("Habari za jioni!"),
        },
        "welcome": P("Karibu {city}!"),
        "welcome_plain": P("Karibu!"),
        "phrases": {
            "thanks": P("Asante sana!", "", "thanks_a_lot"),
            "excuse_me": P("Samahani."),
            "how_much": P("Hii ni bei gani?"),
            "delicious": P("Kitamu sana!"),
            "toilet": P("Choo kiko wapi?"),
            "nice_to_meet": P("Nimefurahi kukutana nawe."),
            "goodbye": P("Kwa heri!"),
            "cheers": P("Afya!", "", "to_your_health"),
        },
    },
    "km": {
        "name": {"id": "Khmer", "en": "Khmer"},
        "latin": False,
        "voices": ("km-KH",),
        "greetings": {
            "hello": P("ជម្រាបសួរ!", "Chumreap suor!"),
            "morning": P("អរុណសួស្តី!", "Arun suostei!"),
            "afternoon": P("ទិវាសួស្តី!", "Tivea suostei!"),
            "evening": P("សាយណ្ហសួស្តី!", "Sayonh suostei!"),
        },
        "welcome": P("សូមស្វាគមន៍មកកាន់{city}!", "Saum svakum mok kan {city}!"),
        "welcome_plain": P("សូមស្វាគមន៍!", "Saum svakum!"),
        "phrases": {
            "thanks": P("អរគុណ!", "Orkun!"),
            "excuse_me": P("សុំទោស។", "Som tous."),
            "how_much": P("នេះថ្លៃប៉ុន្មាន?", "Nih thlai ponman?"),
            "delicious": P("ឆ្ងាញ់ណាស់!", "Chhnganh nas!"),
            "toilet": P("បង្គន់នៅឯណា?", "Bangkon nov ae na?"),
            "nice_to_meet": P("រីករាយដែលបានស្គាល់អ្នក។", "Rikreay del ban skoal neak."),
            "goodbye": P("លាហើយ!", "Lea haeuy!"),
            "cheers": P("ជល់មួយ!", "Chul muoy!"),
        },
    },
}

# Portugal (and the countries that write as Portugal does) says a few things
# differently from Brazil.
LANGUAGES["pt-PT"] = dict(
    LANGUAGES["pt"],
    name={"id": "Portugis", "en": "Portuguese"},
    voices=("pt-PT", "pt-BR"),
    phrases=dict(LANGUAGES["pt"]["phrases"],
                 toilet=P("Onde fica a casa de banho?")),
)


# ------------------------------------------------------------
# Which language a place speaks
# ------------------------------------------------------------

COUNTRY_LANGUAGES = {
    "JP": "ja", "KR": "ko", "KP": "ko", "CN": "zh", "TW": "zh-TW", "HK": "yue", "MO": "yue",
    "TH": "th", "VN": "vi", "MY": "ms", "BN": "ms", "SG": "ms", "PH": "tl", "IN": "hi",
    "KH": "km",
    "SA": "ar", "AE": "ar", "EG": "ar", "JO": "ar", "LB": "ar", "SY": "ar", "IQ": "ar",
    "KW": "ar", "QA": "ar", "BH": "ar", "OM": "ar", "YE": "ar", "MA": "ar", "DZ": "ar",
    "TN": "ar", "LY": "ar", "SD": "ar", "PS": "ar", "MR": "ar",
    "TR": "tr", "RU": "ru", "BY": "ru", "KZ": "ru", "KG": "ru", "UA": "uk",
    "FR": "fr", "BE": "fr", "LU": "fr", "MC": "fr", "SN": "fr", "CI": "fr", "HT": "fr",
    "DE": "de", "AT": "de", "LI": "de", "CH": "de",
    "ES": "es", "MX": "es", "AR": "es", "CO": "es", "PE": "es", "CL": "es", "VE": "es",
    "CU": "es", "EC": "es", "BO": "es", "UY": "es", "PY": "es", "CR": "es", "PA": "es",
    "DO": "es", "GT": "es", "HN": "es", "SV": "es", "NI": "es", "PR": "es",
    "BR": "pt", "PT": "pt-PT", "AO": "pt-PT", "MZ": "pt-PT", "CV": "pt-PT", "TL": "pt-PT",
    "IT": "it", "SM": "it", "VA": "it", "NL": "nl", "SR": "nl",
    "GR": "el", "CY": "el", "SE": "sv", "PL": "pl",
    "GB": "en", "US": "en", "CA": "en", "AU": "en", "NZ": "en", "IE": "en", "ZA": "en", "NG": "en",
    "GH": "en", "JM": "en", "BS": "en", "BB": "en", "TT": "en", "FJ": "en", "MT": "en",
    "PK": "en", "LK": "en",
    "ID": "id", "IL": "he", "IR": "fa", "AF": "fa", "KE": "sw", "TZ": "sw", "UG": "sw",
}

# Cities whose own language differs from their country's (names in any
# language, compared without accents or case).
CITY_LANGUAGES = {
    ("CN", "guangzhou"): "yue", ("CN", "canton"): "yue", ("CN", "kanton"): "yue",
    ("CA", "montreal"): "fr", ("CA", "quebec"): "fr", ("CA", "quebec city"): "fr",
    ("CA", "ville de quebec"): "fr", ("CA", "gatineau"): "fr", ("CA", "trois rivieres"): "fr",
    ("CA", "sherbrooke"): "fr",
    ("BE", "antwerp"): "nl", ("BE", "antwerpen"): "nl", ("BE", "ghent"): "nl",
    ("BE", "gent"): "nl", ("BE", "bruges"): "nl", ("BE", "brugge"): "nl",
    ("BE", "leuven"): "nl", ("BE", "mechelen"): "nl",
    ("CH", "geneva"): "fr", ("CH", "geneve"): "fr", ("CH", "jenewa"): "fr",
    ("CH", "lausanne"): "fr", ("CH", "neuchatel"): "fr", ("CH", "montreux"): "fr",
    ("CH", "lugano"): "it", ("CH", "locarno"): "it", ("CH", "bellinzona"): "it",
    ("IN", "chennai"): "en", ("IN", "bengaluru"): "en", ("IN", "bangalore"): "en",
    ("IN", "kolkata"): "en", ("IN", "calcutta"): "en", ("IN", "kochi"): "en",
    ("IN", "hyderabad"): "en", ("IN", "thiruvananthapuram"): "en", ("IN", "goa"): "en",
    ("IL", "jerusalem"): "ar", ("IL", "yerusalem"): "ar", ("IL", "al quds"): "ar",
    ("PS", "jerusalem"): "ar",
    ("US", "honolulu"): "en",
}

# Indonesian provinces where Javanese is the everyday language.
JAVANESE_REGIONS = ("jawa tengah", "central java", "yogyakarta", "jawa timur", "east java")


def normalize(text):
    """Lower case, accents off, punctuation as spaces: "Québec" -> "quebec"."""
    text = unicodedata.normalize("NFKD", str(text or "")).casefold()
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = "".join(c if c.isalnum() else " " for c in text)
    return " ".join(text.split())


def language_for(country_code, names=(), region=""):
    """The code of the language spoken at a place in `country_code`, known by
    `names` (in any language), in `region`; None when World Trip has none."""
    cc = str(country_code or "").upper()
    for name in names or ():
        found = CITY_LANGUAGES.get((cc, normalize(name)))
        if found:
            return found
    if cc == "ID" and any(r in normalize(region) for r in JAVANESE_REGIONS):
        return "jv"
    return COUNTRY_LANGUAGES.get(cc)


def voice_tags(code, country_code=""):
    """The voice languages (BCP-47) to look for, best first: the language as
    spoken in that country, then the language's own list."""
    entry = LANGUAGES.get(code)
    if entry is None:
        return []
    primary = code.split("-")[0]
    tags = []
    if country_code and code not in ("zh", "zh-TW", "yue"):
        tags.append(f"{primary}-{str(country_code).upper()}")
    for tag in entry["voices"]:
        if tag not in tags:
            tags.append(tag)
    return tags


def any_region(code):
    """Whether any voice of the language family will do (not for Mandarin,
    whose family also holds Cantonese voices)."""
    return LANGUAGES.get(code, {}).get("any_region", True)


def language_name(code, user_language="id"):
    entry = LANGUAGES.get(code)
    if entry is None:
        return ""
    return entry["name"].get(user_language) or entry["name"]["en"]


# ------------------------------------------------------------
# Cities in their own language
# ------------------------------------------------------------

# (country, names people use for it (any language), language, native name,
# transliteration). Latin-script languages only need a row when the native
# name differs, or for the forms below.
NATIVE_CITIES = (
    ("JP", ("tokyo",), "ja", "東京", "Tōkyō"),
    ("JP", ("osaka",), "ja", "大阪", "Ōsaka"),
    ("JP", ("kyoto",), "ja", "京都", "Kyōto"),
    ("JP", ("sapporo",), "ja", "札幌", "Sapporo"),
    ("JP", ("nagoya",), "ja", "名古屋", "Nagoya"),
    ("JP", ("fukuoka",), "ja", "福岡", "Fukuoka"),
    ("JP", ("hiroshima",), "ja", "広島", "Hiroshima"),
    ("JP", ("yokohama",), "ja", "横浜", "Yokohama"),
    ("JP", ("nara",), "ja", "奈良", "Nara"),
    ("JP", ("kobe",), "ja", "神戸", "Kōbe"),
    ("JP", ("naha", "okinawa"), "ja", "那覇", "Naha"),
    ("JP", ("sendai",), "ja", "仙台", "Sendai"),
    ("JP", ("kanazawa",), "ja", "金沢", "Kanazawa"),
    ("JP", ("nagasaki",), "ja", "長崎", "Nagasaki"),
    ("JP", ("hakodate",), "ja", "函館", "Hakodate"),
    ("JP", ("nikko",), "ja", "日光", "Nikkō"),
    ("JP", ("kamakura",), "ja", "鎌倉", "Kamakura"),
    ("KR", ("seoul",), "ko", "서울", "Seoul"),
    ("KR", ("busan", "pusan"), "ko", "부산", "Busan"),
    ("KR", ("incheon",), "ko", "인천", "Incheon"),
    ("KR", ("jeju", "jeju city", "jeju si"), "ko", "제주", "Jeju"),
    ("KR", ("daegu",), "ko", "대구", "Daegu"),
    ("KR", ("gyeongju",), "ko", "경주", "Gyeongju"),
    ("KR", ("daejeon",), "ko", "대전", "Daejeon"),
    ("KR", ("gwangju",), "ko", "광주", "Gwangju"),
    ("KP", ("pyongyang",), "ko", "평양", "Pyeongyang"),
    ("CN", ("beijing", "peking"), "zh", "北京", "Běijīng"),
    ("CN", ("shanghai",), "zh", "上海", "Shànghǎi"),
    ("CN", ("shenzhen",), "zh", "深圳", "Shēnzhèn"),
    ("CN", ("xian", "xi an"), "zh", "西安", "Xī'ān"),
    ("CN", ("chengdu",), "zh", "成都", "Chéngdū"),
    ("CN", ("hangzhou",), "zh", "杭州", "Hángzhōu"),
    ("CN", ("guilin",), "zh", "桂林", "Guìlín"),
    ("CN", ("harbin",), "zh", "哈尔滨", "Hā'ěrbīn"),
    ("CN", ("chongqing",), "zh", "重庆", "Chóngqìng"),
    ("CN", ("nanjing",), "zh", "南京", "Nánjīng"),
    ("CN", ("wuhan",), "zh", "武汉", "Wǔhàn"),
    ("CN", ("kunming",), "zh", "昆明", "Kūnmíng"),
    ("CN", ("tianjin",), "zh", "天津", "Tiānjīn"),
    ("CN", ("xiamen",), "zh", "厦门", "Xiàmén"),
    ("CN", ("suzhou",), "zh", "苏州", "Sūzhōu"),
    ("CN", ("qingdao",), "zh", "青岛", "Qīngdǎo"),
    ("CN", ("lhasa",), "zh", "拉萨", "Lāsà"),
    ("CN", ("guangzhou", "canton", "kanton"), "yue", "廣州", "Gwong2 zau1"),
    ("TW", ("taipei", "taipei city"), "zh-TW", "台北", "Táiběi"),
    ("TW", ("kaohsiung",), "zh-TW", "高雄", "Gāoxióng"),
    ("TW", ("taichung",), "zh-TW", "台中", "Táizhōng"),
    ("TW", ("tainan",), "zh-TW", "台南", "Táinán"),
    ("TW", ("hualien",), "zh-TW", "花蓮", "Huālián"),
    ("HK", ("hong kong", "hongkong"), "yue", "香港", "Hoeng1 gong2"),
    ("MO", ("macau", "macao", "makau"), "yue", "澳門", "Ou3 mun2"),
    ("TH", ("bangkok", "krung thep"), "th", "กรุงเทพฯ", "Krung Thep"),
    ("TH", ("chiang mai",), "th", "เชียงใหม่", "Chiang Mai"),
    ("TH", ("phuket",), "th", "ภูเก็ต", "Phuket"),
    ("TH", ("pattaya",), "th", "พัทยา", "Phatthaya"),
    ("TH", ("ayutthaya", "phra nakhon si ayutthaya"), "th", "อยุธยา", "Ayutthaya"),
    ("TH", ("krabi",), "th", "กระบี่", "Krabi"),
    ("TH", ("chiang rai",), "th", "เชียงราย", "Chiang Rai"),
    ("TH", ("hat yai",), "th", "หาดใหญ่", "Hat Yai"),
    ("TH", ("sukhothai",), "th", "สุโขทัย", "Sukhothai"),
    ("TH", ("hua hin",), "th", "หัวหิน", "Hua Hin"),
    ("SG", ("singapore", "singapura"), "ms", "Singapura", ""),
    ("IN", ("new delhi", "delhi baru"), "hi", "नई दिल्ली", "Nai Dilli"),
    ("IN", ("delhi",), "hi", "दिल्ली", "Dilli"),
    ("IN", ("mumbai", "bombay"), "hi", "मुंबई", "Mumbai"),
    ("IN", ("agra",), "hi", "आगरा", "Agra"),
    ("IN", ("jaipur",), "hi", "जयपुर", "Jaipur"),
    ("IN", ("varanasi", "banaras", "benares"), "hi", "वाराणसी", "Varanasi"),
    ("IN", ("lucknow",), "hi", "लखनऊ", "Lakhnau"),
    ("IN", ("udaipur",), "hi", "उदयपुर", "Udaipur"),
    ("IN", ("jodhpur",), "hi", "जोधपुर", "Jodhpur"),
    ("IN", ("amritsar",), "hi", "अमृतसर", "Amritsar"),
    ("IN", ("pune",), "hi", "पुणे", "Pune"),
    ("IN", ("ahmedabad",), "hi", "अहमदाबाद", "Ahmedabad"),
    ("IN", ("bhopal",), "hi", "भोपाल", "Bhopal"),
    ("IN", ("rishikesh",), "hi", "ऋषिकेश", "Rishikesh"),
    ("IN", ("shimla",), "hi", "शिमला", "Shimla"),
    ("EG", ("cairo", "kairo"), "ar", "القاهرة", "al-Qahira"),
    ("EG", ("alexandria", "aleksandria", "iskandariyah"), "ar", "الإسكندرية", "al-Iskandariyya"),
    ("EG", ("luxor",), "ar", "الأقصر", "al-Uqsur"),
    ("EG", ("giza",), "ar", "الجيزة", "al-Giza"),
    ("AE", ("dubai",), "ar", "دبي", "Dubai"),
    ("AE", ("abu dhabi",), "ar", "أبوظبي", "Abu Dhabi"),
    ("SA", ("riyadh", "riyad"), "ar", "الرياض", "ar-Riyad"),
    ("SA", ("mecca", "makkah", "mekkah", "makkah al mukarramah"), "ar", "مكة المكرمة",
     "Makka al-Mukarrama"),
    ("SA", ("medina", "madinah", "al madinah", "madinah al munawwarah"), "ar",
     "المدينة المنورة", "al-Madina al-Munawwara"),
    ("SA", ("jeddah", "jedda", "jiddah"), "ar", "جدة", "Jidda"),
    ("QA", ("doha",), "ar", "الدوحة", "ad-Dawha"),
    ("JO", ("amman",), "ar", "عمّان", "Amman"),
    ("JO", ("petra", "wadi musa"), "ar", "البتراء", "al-Batra"),
    ("LB", ("beirut",), "ar", "بيروت", "Bayrut"),
    ("IQ", ("baghdad", "bagdad"), "ar", "بغداد", "Baghdad"),
    ("MA", ("marrakesh", "marrakech", "marakesh"), "ar", "مراكش", "Murrakush"),
    ("MA", ("casablanca",), "ar", "الدار البيضاء", "ad-Dar al-Bayda"),
    ("MA", ("fez", "fes"), "ar", "فاس", "Fas"),
    ("MA", ("rabat",), "ar", "الرباط", "ar-Ribat"),
    ("TN", ("tunis",), "ar", "تونس", "Tunis"),
    ("OM", ("muscat",), "ar", "مسقط", "Masqat"),
    ("KW", ("kuwait city", "kuwait"), "ar", "مدينة الكويت", "Madinat al-Kuwait"),
    ("BH", ("manama",), "ar", "المنامة", "al-Manama"),
    ("SY", ("damascus", "damaskus"), "ar", "دمشق", "Dimashq"),
    ("DZ", ("algiers", "aljir"), "ar", "الجزائر", "al-Jaza'ir"),
    ("LY", ("tripoli",), "ar", "طرابلس", "Tarabulus"),
    ("SD", ("khartoum",), "ar", "الخرطوم", "al-Khartum"),
    ("YE", ("sanaa", "sana a"), "ar", "صنعاء", "San'a"),
    ("PS", ("ramallah",), "ar", "رام الله", "Ram Allah"),
    ("PS", ("bethlehem", "betlehem"), "ar", "بيت لحم", "Bayt Lahm"),
    ("IL", ("jerusalem", "yerusalem", "al quds"), "ar", "القدس", "al-Quds"),
    ("PS", ("jerusalem", "yerusalem", "al quds"), "ar", "القدس", "al-Quds"),
    ("IL", ("tel aviv", "tel aviv yafo"), "he", "תל אביב", "Tel Aviv"),
    ("IL", ("haifa",), "he", "חיפה", "Haifa"),
    ("IL", ("eilat",), "he", "אילת", "Eilat"),
    ("IL", ("nazareth",), "he", "נצרת", "Natzrat"),
    ("IR", ("tehran", "teheran"), "fa", "تهران", "Tehran"),
    ("IR", ("isfahan", "esfahan"), "fa", "اصفهان", "Esfahan"),
    ("IR", ("shiraz",), "fa", "شیراز", "Shiraz"),
    ("IR", ("mashhad",), "fa", "مشهد", "Mashhad"),
    ("IR", ("tabriz",), "fa", "تبریز", "Tabriz"),
    ("IR", ("yazd",), "fa", "یزد", "Yazd"),
    ("AF", ("kabul",), "fa", "کابل", "Kabul"),
    ("AF", ("herat",), "fa", "هرات", "Herat"),
    ("KH", ("phnom penh",), "km", "ភ្នំពេញ", "Phnom Penh"),
    ("KH", ("siem reap",), "km", "សៀមរាប", "Siem Reap"),
    ("KH", ("battambang",), "km", "បាត់ដំបង", "Battambang"),
    ("KH", ("kampot",), "km", "កំពត", "Kampot"),
    ("RU", ("moscow", "moskwa", "moskow", "moskva"), "ru", "Москва", "Moskva"),
    ("RU", ("saint petersburg", "st petersburg", "sankt peterburg", "sankt petersburg",
            "petersburg"), "ru", "Санкт-Петербург", "Sankt-Peterburg"),
    ("RU", ("kazan",), "ru", "Казань", "Kazan"),
    ("RU", ("sochi",), "ru", "Сочи", "Sochi"),
    ("RU", ("vladivostok",), "ru", "Владивосток", "Vladivostok"),
    ("RU", ("novosibirsk",), "ru", "Новосибирск", "Novosibirsk"),
    ("RU", ("yekaterinburg", "ekaterinburg"), "ru", "Екатеринбург", "Yekaterinburg"),
    ("RU", ("irkutsk",), "ru", "Иркутск", "Irkutsk"),
    ("RU", ("murmansk",), "ru", "Мурманск", "Murmansk"),
    ("RU", ("kaliningrad",), "ru", "Калининград", "Kaliningrad"),
    ("RU", ("samara",), "ru", "Самара", "Samara"),
    ("RU", ("nizhny novgorod",), "ru", "Нижний Новгород", "Nizhny Novgorod"),
    ("BY", ("minsk",), "ru", "Минск", "Minsk"),
    ("KZ", ("almaty",), "ru", "Алматы", "Almaty"),
    ("KZ", ("astana",), "ru", "Астана", "Astana"),
    ("UA", ("kyiv", "kiev", "kyiv city"), "uk", "Київ", "Kyiv"),
    ("UA", ("lviv", "lvov"), "uk", "Львів", "Lviv"),
    ("UA", ("odesa", "odessa"), "uk", "Одеса", "Odesa"),
    ("UA", ("kharkiv", "kharkov"), "uk", "Харків", "Kharkiv"),
    ("UA", ("dnipro",), "uk", "Дніпро", "Dnipro"),
    ("GR", ("athens", "athena", "athina", "athene"), "el", "Αθήνα", "Athína"),
    ("GR", ("thessaloniki", "salonika"), "el", "Θεσσαλονίκη", "Thessaloníki"),
    ("GR", ("santorini", "thira", "fira"), "el", "Σαντορίνη", "Santoríni"),
    ("GR", ("mykonos",), "el", "Μύκονος", "Mýkonos"),
    ("GR", ("heraklion", "iraklio", "iraklion"), "el", "Ηράκλειο", "Irákleio"),
    ("GR", ("rhodes", "rodos"), "el", "Ρόδος", "Ródos"),
    ("GR", ("corfu", "kerkyra"), "el", "Κέρκυρα", "Kérkyra"),
    ("GR", ("patras", "patra"), "el", "Πάτρα", "Pátra"),
    ("GR", ("chania", "hania"), "el", "Χανιά", "Chaniá"),
    ("CY", ("nicosia", "lefkosia"), "el", "Λευκωσία", "Lefkosía"),
    ("CY", ("limassol", "lemesos"), "el", "Λεμεσός", "Lemesós"),
    ("CY", ("larnaca", "larnaka"), "el", "Λάρνακα", "Lárnaka"),
    ("CY", ("paphos", "pafos"), "el", "Πάφος", "Páfos"),
    ("PL", ("warsaw", "warszawa", "warsawa"), "pl", "Warszawa", ""),
    ("PL", ("krakow", "cracow", "krakau"), "pl", "Kraków", ""),
    ("PL", ("gdansk",), "pl", "Gdańsk", ""),
    ("PL", ("wroclaw",), "pl", "Wrocław", ""),
    ("PL", ("poznan",), "pl", "Poznań", ""),
    ("PL", ("lodz",), "pl", "Łódź", ""),
    ("PL", ("zakopane",), "pl", "Zakopane", ""),
    ("PL", ("torun",), "pl", "Toruń", ""),
    ("PL", ("lublin",), "pl", "Lublin", ""),
    ("PL", ("katowice",), "pl", "Katowice", ""),
    ("PL", ("szczecin",), "pl", "Szczecin", ""),
    ("PL", ("sopot",), "pl", "Sopot", ""),
    ("PL", ("gdynia",), "pl", "Gdynia", ""),
    ("TR", ("istanbul",), "tr", "İstanbul", ""),
    ("TR", ("izmir",), "tr", "İzmir", ""),
    ("TR", ("cappadocia", "kapadokya", "goreme"), "tr", "Kapadokya", ""),
    ("PT", ("lisbon", "lisboa", "lisabon"), "pt-PT", "Lisboa", ""),
    ("PT", ("porto", "oporto"), "pt-PT", "Porto", ""),
    ("BR", ("rio de janeiro", "rio"), "pt", "Rio de Janeiro", ""),
    ("BR", ("sao paulo",), "pt", "São Paulo", ""),
    ("BR", ("brasilia",), "pt", "Brasília", ""),
    ("IT", ("rome", "roma"), "it", "Roma", ""),
    ("IT", ("venice", "venesia", "venezia"), "it", "Venezia", ""),
    ("IT", ("florence", "firenze"), "it", "Firenze", ""),
    ("IT", ("milan", "milano"), "it", "Milano", ""),
    ("IT", ("naples", "napoli"), "it", "Napoli", ""),
    ("IT", ("turin", "torino"), "it", "Torino", ""),
    ("DE", ("munich", "munchen", "muenchen"), "de", "München", ""),
    ("DE", ("cologne", "koln", "koeln"), "de", "Köln", ""),
    ("AT", ("vienna", "wina", "wien"), "de", "Wien", ""),
    ("CH", ("zurich",), "de", "Zürich", ""),
    ("CH", ("geneva", "geneve", "jenewa"), "fr", "Genève", ""),
    ("BE", ("brussels", "brussel", "bruxelles"), "fr", "Bruxelles", ""),
    ("BE", ("antwerp", "antwerpen"), "nl", "Antwerpen", ""),
    ("NL", ("the hague", "den haag"), "nl", "Den Haag", ""),
    ("SE", ("gothenburg", "goteborg"), "sv", "Göteborg", ""),
    ("ES", ("seville", "sevilla"), "es", "Sevilla", ""),
    ("MX", ("mexico city", "kota meksiko", "ciudad de mexico"), "es", "Ciudad de México", ""),
    ("CA", ("montreal",), "fr", "Montréal", ""),
    ("CA", ("quebec", "quebec city"), "fr", "Québec", ""),
)

# Languages that change a city's name after "welcome to": the whole sentence
# for the cities we know (keyed by the native name), else "welcome_plain".
WELCOME_FORMS = {
    "el": {
        "Αθήνα": ("Καλώς ήρθατε στην Αθήνα!", "Kalós írthate stin Athína!"),
        "Θεσσαλονίκη": ("Καλώς ήρθατε στη Θεσσαλονίκη!", "Kalós írthate sti Thessaloníki!"),
        "Σαντορίνη": ("Καλώς ήρθατε στη Σαντορίνη!", "Kalós írthate sti Santoríni!"),
        "Μύκονος": ("Καλώς ήρθατε στη Μύκονο!", "Kalós írthate sti Mýkono!"),
        "Ηράκλειο": ("Καλώς ήρθατε στο Ηράκλειο!", "Kalós írthate sto Irákleio!"),
        "Ρόδος": ("Καλώς ήρθατε στη Ρόδο!", "Kalós írthate sti Ródo!"),
        "Κέρκυρα": ("Καλώς ήρθατε στην Κέρκυρα!", "Kalós írthate stin Kérkyra!"),
        "Πάτρα": ("Καλώς ήρθατε στην Πάτρα!", "Kalós írthate stin Pátra!"),
        "Χανιά": ("Καλώς ήρθατε στα Χανιά!", "Kalós írthate sta Chaniá!"),
        "Λευκωσία": ("Καλώς ήρθατε στη Λευκωσία!", "Kalós írthate sti Lefkosía!"),
        "Λεμεσός": ("Καλώς ήρθατε στη Λεμεσό!", "Kalós írthate sti Lemesó!"),
        "Λάρνακα": ("Καλώς ήρθατε στη Λάρνακα!", "Kalós írthate sti Lárnaka!"),
        "Πάφος": ("Καλώς ήρθατε στην Πάφο!", "Kalós írthate stin Páfo!"),
    },
    "uk": {
        "Київ": ("Ласкаво просимо до Києва!", "Laskavo prosymo do Kyieva!"),
        "Львів": ("Ласкаво просимо до Львова!", "Laskavo prosymo do Lvova!"),
        "Одеса": ("Ласкаво просимо до Одеси!", "Laskavo prosymo do Odesy!"),
        "Харків": ("Ласкаво просимо до Харкова!", "Laskavo prosymo do Kharkova!"),
        "Дніпро": ("Ласкаво просимо до Дніпра!", "Laskavo prosymo do Dnipra!"),
    },
    "pl": {
        "Warszawa": ("Witamy w Warszawie!", ""),
        "Kraków": ("Witamy w Krakowie!", ""),
        "Gdańsk": ("Witamy w Gdańsku!", ""),
        "Wrocław": ("Witamy we Wrocławiu!", ""),
        "Poznań": ("Witamy w Poznaniu!", ""),
        "Łódź": ("Witamy w Łodzi!", ""),
        "Zakopane": ("Witamy w Zakopanem!", ""),
        "Toruń": ("Witamy w Toruniu!", ""),
        "Lublin": ("Witamy w Lublinie!", ""),
        "Katowice": ("Witamy w Katowicach!", ""),
        "Szczecin": ("Witamy w Szczecinie!", ""),
        "Sopot": ("Witamy w Sopocie!", ""),
        "Gdynia": ("Witamy w Gdyni!", ""),
    },
}
_WELCOME_KEYS = {code: {normalize(name): form for name, form in forms.items()}
                 for code, forms in WELCOME_FORMS.items()}

# Portuguese says "ao" before these (masculine, with an article).
PORTUGUESE_WITH_ARTICLE = ("rio de janeiro", "porto", "recife", "cairo", "rio")


def native_city(country_code, names, code):
    """(native name, transliteration) of a city in language `code` from the
    table, or None. `names` are the names the city goes by."""
    cc = str(country_code or "").upper()
    wanted = {normalize(n) for n in names or () if n}
    for row_cc, row_names, row_code, native, translit in NATIVE_CITIES:
        if row_cc == cc and row_code == code and wanted.intersection(row_names):
            return native, translit
    return None


def trim_native(name, code):
    """A localized name without its administrative suffix: 東京都 -> 東京,
    서울특별시 -> 서울, 北京市 -> 北京."""
    name = str(name or "").strip()
    suffixes = {"ja": ("都", "府", "県", "市"), "zh": ("市",), "zh-TW": ("市",), "yue": ("市",),
                "ko": ("특별자치시", "특별시", "광역시", "시")}.get(code, ())
    for suffix in suffixes:
        if name.endswith(suffix) and len(name) > len(suffix) + 1:
            return name[:-len(suffix)]
    return name


def has_latin_letters_only(text):
    """True when every letter of `text` is Latin (a romanized name)."""
    letters = [c for c in str(text or "") if c.isalpha()]
    return bool(letters) and all("LATIN" in unicodedata.name(c, "") for c in letters)


def turkish_dative(name):
    """İstanbul -> İstanbul'a, Ankara -> Ankara'ya, İzmir -> İzmir'e."""
    name = str(name or "").strip()
    vowels = [c for c in name.lower() if c in "aeıioöuüâîû"]
    if not vowels:
        return name
    back = vowels[-1] in "aıouâû"
    suffix = "a" if back else "e"
    if name.lower()[-1] in "aeıioöuüâîû":
        suffix = "y" + suffix
    return f"{name}'{suffix}"


def russian_accusative(name, translit=False):
    """The accusative after "в": Москва -> Москву (Moskva -> Moskvu); names
    ending in a consonant or a soft sign stay as they are."""
    name = str(name or "").strip()
    if translit:
        if name.endswith("ya"):
            return name[:-2] + "yu"
        if name.endswith("a"):
            return name[:-1] + "u"
        return name
    if name.endswith("я"):
        return name[:-1] + "ю"
    if name.endswith("а"):
        return name[:-1] + "у"
    return name


def portuguese_to(name):
    """ "a Lisboa", "ao Rio de Janeiro"."""
    return f"ao {name}" if normalize(name) in PORTUGUESE_WITH_ARTICLE else f"a {name}"


# ------------------------------------------------------------
# Picking greetings and phrases
# ------------------------------------------------------------

def greeting_slot(hour):
    """"morning" (4:00-10:59), "afternoon" (11:00-17:59) or "evening"."""
    if 4 <= hour < 11:
        return "morning"
    if 11 <= hour < 18:
        return "afternoon"
    return "evening"


def _gendered(entry, gender):
    if "male" in entry and "female" in entry:
        return entry["female" if gender == "female" else "male"]
    return entry


def greeting(code, hour, gender=None):
    """The greeting for the local hour in language `code`: {"native",
    "translit", "means"} (means: a MEANINGS key or a dict)."""
    greetings = LANGUAGES[code]["greetings"]
    slot = greeting_slot(hour)
    key = slot
    if slot == "afternoon" and hour >= 15 and "afternoon_late" in greetings:
        key = "afternoon_late"
    found = dict(_gendered(greetings[key], gender))
    if not found.get("means"):
        found["means"] = "afternoon_late" if (slot == "afternoon" and hour >= 15) else key
    return found


def phrase(code, key, gender=None):
    found = dict(_gendered(LANGUAGES[code]["phrases"][key], gender))
    found["means"] = found.get("means") or key
    return found


def welcome(code, native_name=None, translit_name=None):
    """"Welcome to {city}!" in language `code`, {"native", "translit",
    "means"}; the plain "Welcome!" when the city's name isn't known in that
    language (or, for Greek, Polish and Ukrainian, when we don't know how the
    name changes after "welcome to")."""
    entry = LANGUAGES[code]
    if native_name:
        form = _WELCOME_KEYS.get(code, {}).get(normalize(native_name))
        if form is not None:
            return {"native": form[0], "translit": form[1], "means": "welcome"}
        if not entry.get("welcome_forms_only"):
            template = entry["welcome"]
            native_city_to = native_name
            translit_city = translit_name or native_name
            translit_city_to = translit_city
            if code == "tr":
                native_city_to = turkish_dative(native_name)
            elif code == "ru":
                native_city_to = russian_accusative(native_name)
                translit_city_to = russian_accusative(translit_city, translit=True)
            elif code in ("pt", "pt-PT"):
                native_city_to = portuguese_to(native_name)
            native = template["native"].format(city=native_name, city_to=native_city_to)
            translit = template["translit"].format(city=translit_city,
                                                   city_to=translit_city_to) \
                if template["translit"] else ""
            return {"native": native, "translit": translit, "means": "welcome"}
    plain = entry["welcome_plain"]
    return {"native": plain["native"], "translit": plain["translit"], "means": "welcome_plain"}


def meaning(means, user_language="id", city=""):
    """What a greeting or phrase means, in the user's language."""
    lang = user_language if user_language in USER_LANGUAGES else "en"
    if isinstance(means, dict):
        text = means.get(lang) or means.get("en") or ""
    else:
        found = MEANINGS.get(means) or {}
        text = found.get(lang) or found.get("en") or ""
    return text.replace("{city}", str(city or ""))


def spoken_form(item):
    """What the user's own voice reads for an item: the transliteration, or
    the text itself for languages written in Latin letters."""
    return item.get("translit") or item.get("native") or ""


def written_form(item):
    """For Last result: "Konbanwa! (こんばんは！)", or the text itself."""
    native, translit = item.get("native") or "", item.get("translit") or ""
    return f"{translit} ({native})" if translit and translit != native else native
