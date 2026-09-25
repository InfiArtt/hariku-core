# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Plain text a player typed or said, in Indonesian or English, read as one of
the server's commands.

The client reads the commands it knows itself (say, whisper, buy...) and
sends anything else as {"c": "text", "a": ...}; Orbit 1.0's client knows
none of the commands that came later, so the server reads them here, and
every client can use them:

    parse("s")                    -> {"c": "move", "d": "s"}
    parse("u", "id")              -> {"c": "move", "d": "n"}      ("u" is utara)
    parse("u", "en")              -> {"c": "move", "d": "u"}      ("u" is up)
    parse("arah ke kantin")       -> {"c": "way", "a": "kantin"}
    parse("tanam 2 tomat")        -> {"c": "plant", "item": "tomat", "n": 2}
    parse("naik kancil")          -> {"c": "board"}
    parse("terbang ke Karmina")   -> {"c": "fly", "a": "Karmina"}
    parse("dadu 50 tinggi")       -> {"c": "dice", "a": "tinggi", "n": 50}
    parse("tawarkan Budi 3 besi untuk 200 kredit")
                                  -> {"c": "offer", "to": "Budi", "a": "3 besi untuk 200 kredit"}
    parse("beri kredit Budi 50")  -> {"c": "admin", "op": "grant", "to": "Budi", "n": 50}

`find_direction(word, lang)` comes from the world (its direction words), so
the words for directions live in world.json. No I/O.
"""

import re

_TOKEN_RE = re.compile(r"\S+")
_EDGE = ".,!?;:\"'()[]“”‘’"

# (words, meaning), longest first when matched.
VERBS = [
    # moving and finding the way
    (("arah", "ke"), "way"), (("arah", "menuju"), "way"), (("rute", "ke"), "way"), (("rute",), "way"),
    (("jalan", "menuju"), "way"), (("bagaimana", "ke"), "way"), (("gimana", "ke"), "way"),
    (("way", "to"), "way"), (("route", "to"), "way"), (("directions", "to"), "way"),
    (("path", "to"), "way"), (("how", "do", "i", "get", "to"), "way"), (("way",), "way"),
    (("arah",), "way"), (("route",), "way"),
    (("peta",), "map"), (("map",), "map"), (("denah",), "map"), (("peta", "dek"), "map"),
    (("di", "mana", "aku"), "where"), (("dimana", "aku"), "where"), (("di", "mana", "saya"), "where"),
    (("dimana", "saya"), "where"), (("aku", "di", "mana"), "where"), (("saya", "di", "mana"), "where"),
    (("where", "am", "i"), "where"), (("whereami",), "where"), (("location",), "where"),
    (("lokasi",), "where"), (("posisi",), "where"), (("posisiku",), "where"), (("lokasiku",), "where"),
    (("kompas",), "compass"), (("compass",), "compass"), (("heading",), "compass"),
    (("pindai",), "scan"), (("scan",), "scan"), (("memindai",), "scan"),
    (("lacak",), "locate"), (("locate",), "locate"), (("find",), "locate"), (("cari",), "locate"),
    (("di", "mana"), "locate"), (("dimana",), "locate"), (("where", "is"), "locate"),
    (("naik", "kancil"), "board"), (("naik", "shuttle"), "board"), (("naik", "pesawat"), "board"),
    (("naik", "ulang-alik"), "board"), (("board",), "board"), (("board", "the", "kancil"), "board"),
    (("board", "kancil"), "board"), (("board", "shuttle"), "board"), (("board", "the", "shuttle"), "board"),
    (("berangkat",), "board"), (("depart",), "board"), (("ride",), "board"),
    (("ride", "the", "kancil"), "board"), (("ride", "kancil"), "board"), (("ride", "the", "shuttle"), "board"),
    (("ride", "shuttle"), "board"), (("naik", "lift"), "up"),
    (("naik", "tangga"), "up"), (("turun", "tangga"), "down"), (("turun", "lift"), "down"),
    # the temple of the Way of Starlight
    (("bunyikan", "lonceng"), "ring"), (("ring", "bell"), "ring"), (("ring", "the", "bell"), "ring"),
    (("pukul", "lonceng"), "ring"), (("ring", "the", "star", "bell"), "ring"),
    (("bunyikan", "lonceng", "bintang"), "ring"),
    (("nyalakan", "lentera"), "lantern"), (("light", "lantern"), "lantern"),
    (("light", "a", "lantern"), "lantern"), (("light", "the", "lantern"), "lantern"),
    (("nyalakan", "lentera", "bintang"), "lantern"), (("light", "a", "star", "lantern"), "lantern"),
    (("baca",), "read"), (("read",), "read"), (("membaca",), "read"),
    # things
    (("buka",), "open"), (("open",), "open"),
    (("pakai",), "use"), (("use",), "use"), (("gunakan",), "use"), (("minum",), "use"),
    (("drink",), "use"), (("makan",), "use"), (("eat",), "use"), (("nyalakan",), "use"),
    (("pasang",), "equip"), (("equip",), "equip"), (("wear",), "equip"), (("kenakan",), "equip"),
    (("put", "on"), "equip"), (("place",), "equip"), (("set", "beacon"), "equip"),
    (("lepas",), "unequip"), (("lepaskan",), "unequip"), (("copot",), "unequip"),
    (("unequip",), "unequip"), (("take", "off"), "unequip"), (("remove",), "unequip"),
    (("daftar",), "list"), (("list",), "list"), (("stok",), "list"), (("stock",), "list"),
    (("katalog",), "list"), (("catalog",), "list"), (("menu",), "list"),
    (("toko",), "shop"), (("shop",), "shop"), (("belanja",), "shop"),
    # friends and visitors
    (("teman",), "friends"), (("friends",), "friends"), (("daftar", "teman"), "friends"),
    (("tambah", "teman"), "friend_add"), (("add", "friend"), "friend_add"),
    (("hapus", "teman"), "friend_remove"), (("remove", "friend"), "friend_remove"),
    (("unfriend",), "friend_remove"),
    (("undang",), "invite"), (("invite",), "invite"), (("ajak",), "invite"),
    (("usir",), "uninvite"), (("uninvite",), "uninvite"), (("batal", "undang"), "uninvite"),
    (("kunjungi",), "visit"), (("visit",), "visit"), (("mampir", "ke"), "visit"), (("mampir",), "visit"),
    (("bertamu", "ke"), "visit"),
    (("elus",), "pat"), (("pat",), "pat"), (("usap",), "pat"), (("pet",), "pat"),
    (("namai",), "name_pet"), (("name", "pet"), "name_pet"), (("name", "my", "pet"), "name_pet"),
    (("rename", "pet"), "name_pet"),
    (("ganti", "nama"), "name_pet"), (("ganti", "nama", "hewan"), "name_pet"), (("rename",), "name_pet"),
    (("status", "hewan"), "pet_status"), (("status", "peliharaan"), "pet_status"), (("pet", "status"), "pet_status"),
    (("hewanku",), "pet_status"), (("peliharaanku",), "pet_status"), (("my", "pet"), "pet_status"),
    (("my", "pets"), "pet_status"), (("kabar", "hewan"), "pet_status"), (("kabar", "peliharaan"), "pet_status"),
    (("beri", "makan"), "pet_feed"), (("kasih", "makan"), "pet_feed"), (("beri", "pakan"), "pet_feed"),
    (("feed",), "pet_feed"), (("suapi",), "pet_feed"),
    (("main", "dengan"), "pet_play"), (("main", "sama"), "pet_play"), (("bermain", "dengan"), "pet_play"),
    (("bermain", "sama"), "pet_play"), (("ajak", "main"), "pet_play"), (("play", "with"), "pet_play"),
    (("istirahatkan",), "pet_rest"), (("tidurkan",), "pet_rest"), (("rest",), "pet_rest"),
    (("ajari", "trik"), "pet_teach"), (("ajari",), "pet_teach"), (("latih",), "pet_teach"),
    (("teach", "trick"), "pet_teach"), (("teach",), "pet_teach"), (("train",), "pet_teach"),
    (("trik",), "pet_trick"), (("trick",), "pet_trick"), (("tricks",), "pet_trick"), (("do", "trick"), "pet_trick"),
    (("show", "trick"), "pet_trick"), (("perform",), "pet_trick"), (("tunjukkan", "trik"), "pet_trick"),
    (("lakukan", "trik"), "pet_trick"),
    # you, your progress
    (("harian",), "daily"), (("daily",), "daily"), (("bonus", "harian"), "daily"),
    (("daily", "bonus"), "daily"), (("klaim", "harian"), "daily"), (("klaim",), "daily"),
    (("claim",), "daily"), (("claim", "daily"), "daily"), (("hadiah", "harian"), "daily"),
    (("profil",), "profile"), (("profile",), "profile"), (("profilku",), "profile"),
    (("peringkat",), "rank"), (("rank",), "rank"), (("pangkat",), "rank"), (("level",), "rank"),
    (("xp",), "rank"), (("levelku",), "rank"),
    (("suaraku",), "voice"), (("my", "voice"), "voice"), (("suara", "saya"), "voice"),
    (("suara", "ku"), "voice"), (("voice",), "voice"),
    (("kode", "pindah"), "transfer"), (("transfer", "code"), "transfer"),
    (("pindah", "komputer"), "transfer"), (("move", "character"), "transfer"),
    (("move", "my", "character"), "transfer"), (("pindahkan", "karakter"), "transfer"),
    # the farm, mining, salvage
    (("tanam",), "plant"), (("plant",), "plant"), (("menanam",), "plant"), (("sow",), "plant"),
    (("panen",), "harvest"), (("harvest",), "harvest"), (("memanen",), "harvest"), (("petik",), "harvest"),
    (("siram",), "water"), (("water",), "water"), (("sirami",), "water"), (("menyiram",), "water"),
    (("siram", "tanaman"), "water"), (("water", "plants"), "water"),
    (("lahan",), "farm"), (("petak",), "farm"), (("plots",), "farm"), (("my", "plots"), "farm"),
    (("farm",), "farm"), (("my", "farm"), "farm"), (("lahanku",), "farm"), (("kebunku",), "farm"),
    (("tambang",), "mine"), (("mine",), "mine"), (("menambang",), "mine"), (("gali",), "mine"),
    (("dig",), "mine"),
    (("kumpulkan",), "collect"), (("collect",), "collect"), (("salvage",), "collect"),
    (("pulung",), "collect"), (("memulung",), "collect"), (("kais",), "collect"),
    # travel between worlds, ships
    (("dunia",), "worlds"), (("worlds",), "worlds"), (("planets",), "worlds"), (("planet",), "worlds"),
    (("daftar", "dunia"), "worlds"), (("list", "worlds"), "worlds"), (("semua", "dunia"), "worlds"),
    (("gerbang",), "gate"), (("gerbang", "ke"), "gate"), (("masuk", "gerbang"), "gate"),
    (("masuk", "gerbang", "ke"), "gate"), (("lewat", "gerbang", "ke"), "gate"), (("gate",), "gate"),
    (("gate", "to"), "gate"), (("enter", "the", "gate", "to"), "gate"),
    (("step", "through", "the", "gate", "to"), "gate"),
    (("take", "the", "gate", "to"), "gate"), (("use", "the", "gate", "to"), "gate"),
    (("feri",), "ferry"), (("feri", "ke"), "ferry"), (("naik", "feri"), "ferry"), (("naik", "feri", "ke"), "ferry"),
    (("ferry",), "ferry"), (("ferry", "to"), "ferry"), (("take", "the", "ferry", "to"), "ferry"),
    (("ride", "the", "ferry", "to"), "ferry"), (("catch", "the", "ferry", "to"), "ferry"),
    (("take", "the", "ferry"), "ferry"), (("ride", "the", "ferry"), "ferry"),
    (("naik", "kapal"), "embark"), (("masuk", "kapal"), "embark"), (("naik", "ke", "kapal"), "embark"),
    (("masuk", "ke", "kapal"), "embark"), (("embark",), "embark"), (("go", "aboard"), "embark"),
    (("board", "ship"), "embark"), (("board", "my", "ship"), "embark"), (("enter", "my", "ship"), "embark"),
    (("get", "in", "the", "ship"), "embark"), (("aboard",), "embark"),
    (("turun", "kapal"), "disembark"), (("turun", "dari", "kapal"), "disembark"), (("keluar", "kapal"), "disembark"),
    (("keluar", "dari", "kapal"), "disembark"), (("disembark",), "disembark"), (("leave", "the", "ship"), "disembark"),
    (("leave", "ship"), "disembark"), (("get", "off", "the", "ship"), "disembark"), (("turun", "feri"), "disembark"),
    (("turun", "dari", "feri"), "disembark"), (("get", "off", "the", "ferry"), "disembark"),
    (("terbang", "ke"), "fly"), (("fly", "to"), "fly"), (("set", "course", "for"), "fly"),
    (("set", "course", "to"), "fly"), (("berlayar", "ke"), "fly"), (("berangkat", "ke"), "fly"),
    (("launch", "to"), "fly"), (("terbangkan", "kapal", "ke"), "fly"),
    (("isi", "bahan", "bakar"), "refuel"), (("isi", "bensin"), "refuel"), (("isi", "tangki"), "refuel"),
    (("tambah", "bahan", "bakar"), "refuel"), (("refuel",), "refuel"), (("fuel", "up"), "refuel"),
    (("muat",), "load"), (("muatkan",), "load"), (("load",), "load"),
    (("bongkar",), "unload"), (("bongkar", "muatan"), "unload"), (("unload",), "unload"),
    (("kargo",), "cargo"), (("cargo",), "cargo"), (("palka",), "cargo"), (("kapalku",), "cargo"),
    (("my", "ship"), "cargo"), (("status", "kapal"), "cargo"), (("ship", "status"), "cargo"),
    (("namai", "kapal"), "name_ship"), (("name", "ship"), "name_ship"), (("name", "my", "ship"), "name_ship"),
    (("rename", "ship"), "name_ship"), (("beri", "nama", "kapal"), "name_ship"),
    # the other worlds' work
    (("hadapi",), "face"), (("temui",), "face"), (("dekati",), "face"), (("face",), "face"),
    (("approach",), "face"),
    (("gig",), "gig"), (("ambil", "gig"), "gig"), (("take", "a", "gig"), "gig"), (("kurir",), "gig"),
    (("courier", "job"), "gig"), (("antar", "paket"), "gig"), (("delivery",), "gig"),
    # the hunt
    (("perburuan",), "hunt"), (("hunt",), "hunt"), (("the", "hunt"), "hunt"), (("nada", "yang", "hilang"), "hunt"),
    (("lost", "chord"), "hunt"), (("the", "lost", "chord"), "hunt"),
    (("selidiki",), "investigate"), (("investigate",), "investigate"), (("telusuri",), "investigate"),
    (("look", "for", "clues"), "investigate"), (("cari", "petunjuk"), "investigate"),
    (("pecahkan",), "solve"), (("solve",), "solve"), (("jawaban",), "solve"), (("my", "answer", "is"), "solve"),
    (("jawabanku",), "solve"),
    (("papan", "pemburu"), "hunt_board"), (("hunt", "board"), "hunt_board"), (("hunters",), "hunt_board"),
    (("para", "pemburu"), "hunt_board"),
    (("status", "perburuan"), "hunt_status"), (("hunt", "status"), "hunt_status"),
    (("musim", "baru"), "new_season"), (("new", "season"), "new_season"),
    (("umumkan", "petunjuk"), "release_hint"), (("release", "hint"), "release_hint"),
    (("uji", "perburuan"), "hunt_test"), (("hunt", "test"), "hunt_test"),
    # events
    (("acara",), "events"), (("events",), "events"), (("event",), "events"), (("agenda",), "events"),
    (("daftar", "acara"), "events"), (("what's", "on"), "events"), (("whats", "on"), "events"),
    (("ikut",), "join"), (("join",), "join"), (("gabung",), "join"), (("ikut", "acara"), "join"),
    (("join", "event"), "join"), (("join", "in"), "join"), (("buka", "hadiah"), "join"),
    (("open", "gift"), "join"),
    (("dengar",), "listen"), (("dengarkan",), "listen"), (("listen",), "listen"), (("listen", "for"), "listen"),
    (("tangkap",), "catch"), (("catch",), "catch"), (("tangkap", "robot"), "catch"), (("catch", "robot"), "catch"),
    (("catch", "the", "robot"), "catch"),
    (("geledah",), "search"), (("search",), "search"), (("geledah", "ruangan"), "search"),
    (("search", "room"), "search"), (("search", "the", "room"), "search"),
    (("tonton",), "watch"), (("watch",), "watch"), (("tonton", "komet"), "watch"), (("watch", "comet"), "watch"),
    (("watch", "the", "comet"), "watch"),
    (("tonton", "kembang", "api"), "watch"), (("watch", "fireworks"), "watch"),
    (("adakan", "pesta"), "party"), (("bikin", "pesta"), "party"), (("host", "party"), "party"),
    (("host", "a", "party"), "party"), (("throw", "a", "party"), "party"), (("throw", "party"), "party"),
    (("perbaiki", "drone"), "fix"), (("fix", "drone"), "fix"), (("fix", "the", "drone"), "fix"),
    (("repair", "drone"), "fix"), (("repair", "the", "drone"), "fix"), (("matikan", "drone"), "fix"),
    (("mulai", "event"), "event_start"), (("mulai", "acara"), "event_start"), (("start", "event"), "event_start"),
    (("hentikan", "event"), "event_stop"), (("hentikan", "acara"), "event_stop"), (("stop", "event"), "event_stop"),
    (("batalkan", "acara"), "event_stop"), (("cancel", "event"), "event_stop"),
    (("jadwalkan", "event"), "event_schedule"), (("jadwalkan", "acara"), "event_schedule"),
    (("schedule", "event"), "event_schedule"),
    # the casino
    (("kasino",), "casino"), (("casino",), "casino"), (("menu", "kasino"), "casino"),
    (("casino", "menu"), "casino"),
    (("dadu",), "dice"), (("lempar", "dadu"), "dice"), (("main", "dadu"), "dice"), (("kocok", "dadu"), "dice"),
    (("dice",), "dice"), (("roll",), "dice"), (("roll", "dice"), "dice"), (("roll", "the", "dice"), "dice"),
    (("play", "dice"), "dice"),
    (("slot",), "slots"), (("slots",), "slots"), (("main", "slot"), "slots"), (("mesin", "slot"), "slots"),
    (("putar", "slot"), "slots"), (("play", "slots"), "slots"), (("play", "the", "slots"), "slots"),
    (("spin",), "slots"), (("slot", "machine"), "slots"),
    (("blackjack",), "blackjack"), (("main", "blackjack"), "blackjack"), (("play", "blackjack"), "blackjack"),
    (("bj",), "blackjack"), (("main", "kartu"), "blackjack"),
    (("hit",), "hit"), (("hit", "me"), "hit"), (("tambah", "kartu"), "hit"), (("kartu", "lagi"), "hit"),
    (("minta", "kartu"), "hit"), (("another", "card"), "hit"), (("one", "more", "card"), "hit"),
    (("stand",), "stand"), (("cukup",), "stand"), (("sudah", "cukup"), "stand"),
    (("i", "stand"), "stand"),
    (("tantang",), "challenge"), (("challenge",), "challenge"), (("lempar", "koin"), "challenge"),
    (("coinflip",), "challenge"), (("coin", "flip"), "challenge"), (("flip", "a", "coin"), "challenge"),
    (("adu", "koin"), "challenge"),
    (("lotre",), "lottery"), (("lottery",), "lottery"), (("undian",), "lottery"), (("lotere",), "lottery"),
    (("lotre", "mingguan"), "lottery"), (("weekly", "lottery"), "lottery"),
    # the arcade (after the casino's "main dadu": longer phrases are matched first)
    (("arkade",), "arcade"), (("arcade",), "arcade"), (("the", "arcade"), "arcade"),
    (("main",), "play"), (("play",), "play"), (("mainkan",), "play"),
    (("berhenti", "main"), "stop_game"), (("stop", "game"), "stop_game"), (("stop", "playing"), "stop_game"),
    (("stop", "the", "game"), "stop_game"), (("quit", "game"), "stop_game"), (("udahan", "main"), "stop_game"),
    (("skor", "arkade"), "high_scores"), (("rekor", "arkade"), "high_scores"),
    (("papan", "skor", "arkade"), "high_scores"), (("skor", "tertinggi"), "high_scores"),
    (("arcade", "scores"), "high_scores"), (("arcade", "high", "scores"), "high_scores"),
    # crews
    (("kru",), "crew"), (("crew",), "crew"), (("my", "crew"), "crew"), (("kruku",), "crew"),
    (("info", "kru"), "crew"), (("crew", "info"), "crew"),
    (("buat", "kru"), "crew_create"), (("bentuk", "kru"), "crew_create"), (("dirikan", "kru"), "crew_create"),
    (("crew", "create"), "crew_create"), (("create", "crew"), "crew_create"), (("found", "a", "crew"), "crew_create"),
    (("start", "a", "crew"), "crew_create"), (("kru", "buat"), "crew_create"),
    (("undang", "ke", "kru"), "crew_invite"), (("kru", "undang"), "crew_invite"), (("crew", "invite"), "crew_invite"),
    (("invite", "to", "crew"), "crew_invite"), (("ajak", "ke", "kru"), "crew_invite"),
    (("kru", "bilang"), "crew_say"), (("bilang", "ke", "kru"), "crew_say"), (("bilang", "kru"), "crew_say"),
    (("crew", "say"), "crew_say"), (("say", "to", "crew"), "crew_say"), (("cs",), "crew_say"),
    (("keluar", "kru"), "crew_leave"), (("keluar", "dari", "kru"), "crew_leave"), (("kru", "keluar"), "crew_leave"),
    (("crew", "leave"), "crew_leave"), (("leave", "crew"), "crew_leave"), (("leave", "the", "crew"), "crew_leave"),
    (("keluarkan", "dari", "kru"), "crew_kick"), (("kru", "keluarkan"), "crew_kick"), (("crew", "kick"), "crew_kick"),
    (("crew", "remove"), "crew_kick"), (("kick", "from", "crew"), "crew_kick"),
    (("jadikan", "kapten"), "crew_captain"), (("kru", "kapten"), "crew_captain"),
    (("crew", "captain"), "crew_captain"), (("make", "captain"), "crew_captain"),
    (("moto", "kru"), "crew_motto"), (("kru", "moto"), "crew_motto"), (("crew", "motto"), "crew_motto"),
    (("daftar", "kru"), "crews"), (("papan", "kru"), "crews"), (("crews",), "crews"), (("crew", "board"), "crews"),
    (("top", "crews"), "crews"), (("peringkat", "kru"), "crews"),
    (("bubarkan", "kru"), "crew_disband"), (("disband", "crew"), "crew_disband"),
    # duels
    (("duel",), "duel"), (("tantang", "duel"), "duel"), (("ajak", "duel"), "duel"),
    (("challenge", "to", "a", "duel"), "duel"),
    (("duel", "with"), "duel"), (("duel", "dengan"), "duel"), (("adu", "cepat", "dengan"), "duel"),
    (("duels", "off"), "duels_off"), (("duel", "off"), "duels_off"), (("no", "duels"), "duels_off"),
    (("matikan", "duel"), "duels_off"), (("duel", "mati"), "duels_off"),
    (("duels", "on"), "duels_on"), (("duel", "on"), "duels_on"), (("nyalakan", "duel"), "duels_on"),
    (("duel", "nyala"), "duels_on"), (("duels",), "duels"), (("status", "duel"), "duels"),
    (("hentikan", "duel"), "duel_stop"), (("stop", "duel"), "duel_stop"), (("stop", "the", "duel"), "duel_stop"),
    # the residents (characters who are not players)
    (("bicara", "dengan"), "talk"), (("bicara", "sama"), "talk"), (("berbicara", "dengan"), "talk"),
    (("ngobrol", "dengan"), "talk"), (("ngobrol", "sama"), "talk"), (("mengobrol", "dengan"), "talk"),
    (("ajak", "bicara"), "talk"), (("ajak", "ngobrol"), "talk"), (("talk", "to"), "talk"),
    (("talk", "with"), "talk"), (("speak", "to"), "talk"), (("speak", "with"), "talk"), (("chat", "with"), "talk"),
    (("chat", "to"), "talk"), (("talk",), "talk"),
    (("tanya",), "ask"), (("tanyakan",), "ask"), (("tanya", "ke"), "ask"), (("tanya", "pada"), "ask"),
    (("tanya", "sama"), "ask"), (("tanya", "kepada"), "ask"), (("bertanya", "pada"), "ask"),
    (("bertanya", "kepada"), "ask"), (("bertanya", "ke"), "ask"), (("ask",), "ask"),
    (("sapa",), "greet"), (("menyapa",), "greet"), (("greet",), "greet"), (("say", "hi", "to"), "greet"),
    (("say", "hello", "to"), "greet"),
    (("penduduk",), "residents"), (("residents",), "residents"), (("warga",), "residents"), (("npc",), "residents"),
    (("npcs",), "residents"), (("daftar", "penduduk"), "residents"), (("who", "lives", "here"), "residents"),
    # families
    (("pasangan",), "partner"), (("pasanganku",), "partner"), (("partner",), "partner"), (("my", "partner"), "partner"),
    (("status", "pasangan"), "partner"), (("partnership",), "partner"),
    (("ajak", "berpasangan"), "partner_ask"), (("jadikan", "pasangan"), "partner_ask"),
    (("berpasangan", "dengan"), "partner_ask"), (("partner", "with"), "partner_ask"),
    (("partner", "up", "with"), "partner_ask"), (("be", "partners", "with"), "partner_ask"),
    (("akhiri", "kemitraan"), "partner_end"), (("akhiri", "pasangan"), "partner_end"),
    (("end", "partnership"), "partner_end"), (("end", "the", "partnership"), "partner_end"),
    (("konfirmasi", "akhiri"), "partner_end_confirm"), (("confirm", "end"), "partner_end_confirm"),
    (("adopsi",), "adopt"), (("adopsi", "anak"), "adopt"), (("adopsi", "bayi"), "adopt"), (("adopt",), "adopt"),
    (("adopt", "a", "baby"), "adopt"), (("adopt", "a", "child"), "adopt"),
    (("keluarga",), "family"), (("keluargaku",), "family"), (("family",), "family"), (("my", "family"), "family"),
    (("anak",), "family"), (("anakku",), "family"), (("status", "anak"), "family"), (("child",), "family"),
    (("children",), "family"), (("my", "child"), "family"), (("my", "children"), "family"),
    (("bacakan", "cerita"), "child_story"), (("bacakan", "dongeng"), "child_story"),
    (("ceritakan", "dongeng"), "child_story"), (("read", "a", "story"), "child_story"),
    (("tell", "a", "story"), "child_story"), (("read", "a", "story", "to"), "child_story"),
    (("tell", "a", "story", "to"), "child_story"),
    (("minta", "tolong"), "child_fetch"), (("mintai", "tolong"), "child_fetch"),
    (("bawa",), "child_take"), (("gendong",), "child_take"), (("bring",), "child_take"),
    (("upacara", "nama"), "naming"), (("upacara", "pemberian", "nama"), "naming"), (("naming", "rite"), "naming"),
    (("naming", "ceremony"), "naming"), (("name", "the", "baby"), "naming"), (("name", "baby"), "naming"),
    (("namai", "bayi"), "naming"), (("namai", "anak"), "naming"),
    # weddings
    (("lamar",), "propose"), (("melamar",), "propose"), (("propose", "to"), "propose"), (("propose",), "propose"),
    (("pernikahan",), "wedding"), (("pernikahanku",), "wedding"), (("wedding",), "wedding"),
    (("my", "wedding"), "wedding"), (("our", "wedding"), "wedding"),
    (("pesan", "pernikahan"), "wedding_book"), (("pesan", "venue"), "wedding_book"), (("pesan", "aula"), "wedding_book"),
    (("book", "wedding"), "wedding_book"), (("book", "a", "wedding"), "wedding_book"),
    (("book", "the", "wedding"), "wedding_book"), (("book", "our", "wedding"), "wedding_book"),
    (("book", "venue"), "wedding_book"),
    (("batalkan", "pernikahan"), "wedding_cancel"), (("batal", "pernikahan"), "wedding_cancel"),
    (("cancel", "wedding"), "wedding_cancel"), (("cancel", "the", "wedding"), "wedding_cancel"),
    (("cancel", "our", "wedding"), "wedding_cancel"),
    (("jadwal", "pernikahan"), "wedding_schedule"), (("wedding", "schedule"), "wedding_schedule"),
    (("weddings",), "wedding_schedule"), (("daftar", "pernikahan"), "wedding_schedule"),
    (("undangan",), "wedding_invitations"), (("undanganku",), "wedding_invitations"),
    (("invitations",), "wedding_invitations"), (("my", "invitations"), "wedding_invitations"),
    (("hadir",), "wedding_rsvp_yes"), (("rsvp", "yes"), "wedding_rsvp_yes"), (("aku", "datang"), "wedding_rsvp_yes"),
    (("saya", "datang"), "wedding_rsvp_yes"), (("i'll", "come"), "wedding_rsvp_yes"), (("i", "will", "come"), "wedding_rsvp_yes"),
    (("tidak", "hadir"), "wedding_rsvp_no"), (("rsvp", "no"), "wedding_rsvp_no"), (("tidak", "bisa", "hadir"), "wedding_rsvp_no"),
    (("can't", "come"), "wedding_rsvp_no"), (("cannot", "come"), "wedding_rsvp_no"), (("i", "can't", "come"), "wedding_rsvp_no"),
    (("lempar", "bunga"), "wedding_flowers"), (("tabur", "bunga"), "wedding_flowers"),
    (("taburkan", "bunga"), "wedding_flowers"), (("throw", "flowers"), "wedding_flowers"),
    (("throw", "petals"), "wedding_flowers"),
    (("ikrar",), "wedding_vow"), (("janji",), "wedding_vow"), (("janjiku",), "wedding_vow"), (("vow",), "wedding_vow"),
    (("my", "vow"), "wedding_vow"), (("my", "vow", "is"), "wedding_vow"),
    (("satukan", "cahaya"), "wedding_join"), (("satukan", "lentera"), "wedding_join"),
    (("join", "the", "lights"), "wedding_join"), (("join", "lights"), "wedding_join"),
    (("join", "the", "lanterns"), "wedding_join"),
    (("ya",), "wedding_yes"), (("yes",), "wedding_yes"), (("bersedia",), "wedding_yes"),
    (("saya", "bersedia"), "wedding_yes"), (("aku", "bersedia"), "wedding_yes"),
    (("tidak",), "wedding_no"), (("no",), "wedding_no"),
    (("tanda", "tangan"), "wedding_sign"), (("tandatangani",), "wedding_sign"), (("tanda", "tangani"), "wedding_sign"),
    (("sign",), "wedding_sign"), (("sign", "the", "register"), "wedding_sign"),
    (("baca", "kenangan"), "wedding_memory"), (("kenangan",), "wedding_memory"), (("kenanganku",), "wedding_memory"),
    (("read", "memory"), "wedding_memory"), (("read", "the", "memory"), "wedding_memory"),
    (("read", "memories"), "wedding_memory"), (("memory",), "wedding_memory"), (("memories",), "wedding_memory"),
    (("wedding", "memory"), "wedding_memory"),
    # trading (and anything waiting for a yes)
    (("terima",), "accept"), (("accept",), "accept"), (("terima", "tawaran"), "accept"),
    (("accept", "offer"), "accept"), (("terima", "tantangan"), "accept"), (("accept", "challenge"), "accept"),
    (("tawarkan",), "offer"), (("tawari",), "offer"), (("offer",), "offer"), (("tukar",), "offer"),
    (("trade",), "offer"), (("barter",), "offer"),
    (("tolak",), "decline"), (("decline",), "decline"), (("refuse",), "decline"), (("reject",), "decline"),
    (("menolak",), "decline"), (("tolak", "tawaran"), "decline"), (("decline", "offer"), "decline"),
    (("tolak", "tantangan"), "decline"),
    (("batalkan", "tawaran"), "cancel_offer"), (("batal", "tawaran"), "cancel_offer"),
    (("tarik", "tawaran"), "cancel_offer"), (("cancel", "offer"), "cancel_offer"),
    (("withdraw", "offer"), "cancel_offer"), (("cancel", "challenge"), "cancel_offer"),
    (("batalkan", "tantangan"), "cancel_offer"), (("batal", "tantangan"), "cancel_offer"),
    # achievements, leaderboards
    (("prestasi",), "achievements"), (("prestasiku",), "achievements"), (("pencapaian",), "achievements"),
    (("achievements",), "achievements"), (("achievement",), "achievements"),
    (("my", "achievements"), "achievements"), (("badges",), "achievements"), (("lencana",), "achievements"),
    (("papan", "skor"), "leaderboard"), (("papan", "peringkat"), "leaderboard"),
    (("peringkat", "teratas"), "leaderboard"), (("klasemen",), "leaderboard"),
    (("leaderboard",), "leaderboard"), (("leaderboards",), "leaderboard"), (("scoreboard",), "leaderboard"),
    (("high", "scores"), "leaderboard"), (("top", "players"), "leaderboard"), (("top",), "leaderboard"),
    (("lihat", "papan", "skor"), "leaderboard"), (("skor",), "leaderboard"),
    # help, the status
    (("bantuan",), "help"), (("help",), "help"),
    (("status",), "status"), (("status", "orbit"), "status"), (("orbit", "status"), "status"),
    # admin (the game checks who may)
    (("grant",), "grant"), (("beri", "kredit"), "grant"), (("hibah",), "grant"),
    (("grant", "credits"), "grant"),
    (("ambil", "kredit"), "take_credits"), (("take", "credits"), "take_credits"),
    (("beri", "item"), "give_item"), (("give", "item"), "give_item"), (("spawn",), "give_item"),
    (("ekonomi",), "economy"), (("economy",), "economy"),
    (("atur", "harga"), "set_price"), (("set", "price"), "set_price"),
    (("reset", "harian"), "reset_streak"), (("reset", "streak"), "reset_streak"),
    (("reset", "beruntun"), "reset_streak"),
    (("goto",), "goto"), (("teleport",), "goto"), (("tp",), "goto"),
    (("tak", "terlihat"), "invisible"), (("invisible",), "invisible"), (("siluman",), "invisible"),
    (("pindahan",), "transfers"), (("transfers",), "transfers"),
    (("cabut", "akses"), "revoke"), (("revoke",), "revoke"),
    (("kode", "pindah", "untuk"), "transfer_for"), (("transfer", "code", "for"), "transfer_for"),
    (("log", "admin"), "admin_log"), (("admin", "log"), "admin_log"),
]
VERBS.sort(key=lambda entry: -len(entry[0]))

ADMIN_OPS = {"grant", "take_credits", "give_item", "economy", "set_price", "reset_streak", "goto",
             "invisible", "transfers", "revoke", "transfer_for", "admin_log", "event_start", "event_stop",
             "event_schedule", "hunt_status", "new_season", "release_hint", "hunt_test", "crew_disband",
             "duel_stop"}
BOARD_WORDS = {"kancil", "shuttle", "pesawat", "ulang-alik"}
_ALL_WORDS = {"all", "semua", "semuanya", "everything"}


def _tokens(text):
    """[(start, end, word)]: each word lower-cased, without punctuation around it."""
    found = []
    for m in _TOKEN_RE.finditer(text):
        word = m.group().lower().strip(_EDGE)
        if word:
            found.append((m.start(), m.end(), word))
    return found


def _number(word):
    try:
        return int(word)
    except (TypeError, ValueError):
        return None


def _word(text, token):
    return text[token[0]:token[1]].strip(_EDGE)


def _rest(text, tokens, index):
    return text[tokens[index][0]:].strip() if index < len(tokens) else ""


def _thing_and_count(tokens, index, allow_all=False):
    """ "2 tomat", "tomat 2", "semua tomat" -> (item words, n or None or "all")."""
    n = None
    words = []
    for _s, _e, word in tokens[index:]:
        if n is None and _number(word) is not None:
            n = _number(word)
        elif n is None and allow_all and word in _ALL_WORDS:
            n = "all"
        else:
            words.append(word)
    return " ".join(words), n


def _name_and_rest(text, tokens, index):
    """The first word (a player's name, in its own case) and what follows."""
    if index >= len(tokens):
        return "", ""
    return _word(text, tokens[index]), _rest(text, tokens, index + 1)


def parse(text, lang="en", find_direction=None):
    """The command in `text`, or None when there is none here."""
    text = " ".join(str(text or "").split())
    tokens = _tokens(text)
    if not tokens:
        return None
    if find_direction is not None:
        d = find_direction(" ".join(t[2] for t in tokens), lang)
        if d:
            return {"c": "move", "d": d}
        if len(tokens) >= 2 and tokens[0][2] in ("go", "walk", "pergi", "jalan", "ke", "head"):
            d = find_direction(" ".join(t[2] for t in tokens[1:]), lang)
            if d:
                return {"c": "move", "d": d}
    words = [t[2] for t in tokens]
    meaning, used = None, 0
    for phrase, what in VERBS:
        if tuple(words[:len(phrase)]) == phrase:
            meaning, used = what, len(phrase)
            break
    if meaning is None:
        return None
    rest = _rest(text, tokens, used)
    if meaning == "up":
        return {"c": "move", "d": "u"}
    if meaning == "down":
        return {"c": "move", "d": "d"}
    if meaning == "way":
        if not rest and words[0] == "arah":
            return {"c": "compass"}
        return {"c": "way", "a": rest}
    if meaning in ("map", "where", "compass", "scan", "board", "daily", "rank", "harvest", "water",
                   "farm", "mine", "collect", "transfer", "friends", "status", "casino", "hit", "stand",
                   "lottery", "decline", "cancel_offer", "worlds", "disembark", "cargo", "gig", "events",
                   "join", "listen", "catch", "search", "watch", "party", "hunt", "investigate", "hunt_board"):
        if meaning == "board" and used == 1 and words[0] == "naik" and rest:
            return None
        return {"c": meaning}
    if meaning == "locate":
        if not rest:
            return {"c": "where"}
        return {"c": "locate", "to": _word(text, tokens[used])}
    if meaning in ("friend_add", "friend_remove"):
        name, _more = _name_and_rest(text, tokens, used)
        return {"c": "friends", "op": "add" if meaning == "friend_add" else "remove", "to": name}
    if meaning in ("invite", "uninvite", "visit"):
        name, more = _name_and_rest(text, tokens, used)
        if meaning == "visit":
            return {"c": "visit", "to": name}
        if meaning == "invite" and {"kru", "crew", "kruku"} & set(more.lower().split()):
            return {"c": "crew_invite", "to": name}          # "undang Budi ke kru"
        if meaning == "invite" and WEDDING_WORDS & set(more.lower().strip(".,!?").split()):
            return {"c": "wedding", "op": "invite", "to": name}     # "undang Budi ke pernikahan"
        return {"c": "invite", "op": "remove" if meaning == "uninvite" else "add", "to": name}
    if meaning == "pat":
        return {"c": "pet", "op": "pat"}
    if meaning == "name_pet":
        return {"c": "pet", "op": "name", "a": rest}
    if meaning.startswith("pet_"):
        return {"c": "pet", "op": meaning[4:], "a": rest}
    if meaning == "open":
        return {"c": "open", "a": rest}
    if meaning == "ring":
        return {"c": "ring"}
    if meaning == "lantern":
        return {"c": "lantern"}
    if meaning == "read":
        return {"c": "look", "a": rest} if rest else None
    if meaning in ("use", "equip", "unequip"):
        message = {"c": "unequip" if meaning == "unequip" else "use", "item": rest}
        if meaning == "equip":
            message["equip"] = True
        return message
    if meaning in ("list", "shop"):
        return {"c": "list", "a": rest}
    if meaning == "profile":
        return {"c": "profile", "to": _word(text, tokens[used]) if used < len(tokens) else ""}
    if meaning == "voice":
        return {"c": "voice", "a": rest}
    if meaning == "plant":
        item, n = _thing_and_count(tokens, used)
        message = {"c": "plant", "item": item}
        if n is not None:
            message["n"] = n
        return message
    if meaning == "help":
        return {"c": "help", "a": rest}
    if meaning in ("dice", "slots", "blackjack"):
        choice, n = _thing_and_count(tokens, used)
        message = {"c": meaning}
        if choice and meaning == "dice":
            message["a"] = choice
        if n is not None:
            message["n"] = n
        return message
    if meaning == "challenge":
        name, _more = _name_and_rest(text, tokens, used)
        message = {"c": "challenge", "to": name}
        numbers = [_number(t[2]) for t in tokens[used + 1:] if _number(t[2]) is not None]
        if numbers:
            message["n"] = numbers[0]
        return message
    if meaning == "accept":
        numbers = [_number(t[2]) for t in tokens[used:] if _number(t[2]) is not None]
        return {"c": "accept", "n": numbers[0]} if numbers else {"c": "accept"}
    if meaning == "offer":
        name, more = _name_and_rest(text, tokens, used)
        return {"c": "offer", "to": name, "a": more}
    if meaning in ("gate", "ferry", "fly", "face", "name_ship"):
        return {"c": meaning, "a": rest}
    if meaning == "fix":
        return {"c": "work"}
    if meaning == "solve":
        return {"c": "solve", "a": rest}
    if meaning == "play":
        return {"c": "play", "a": rest, "raw": text}       # "main street" is a place, not a game
    if meaning == "high_scores":
        return {"c": "high_scores", "a": rest}
    if meaning in ("arcade", "stop_game", "crew", "crew_leave", "crews", "duels"):
        return {"c": meaning}
    if meaning in ("duels_on", "duels_off"):
        return {"c": "duels", "op": meaning[6:]}
    if meaning == "duel":
        name, _more = _name_and_rest(text, tokens, used)
        message = {"c": "duel", "to": name}
        numbers = [_number(t[2]) for t in tokens[used + 1:] if _number(t[2]) is not None]
        if numbers:
            message["n"] = numbers[0]
        return message
    if meaning in ("crew_create", "crew_say", "crew_motto"):
        return {"c": meaning, "a": rest}
    if meaning in ("crew_invite", "crew_kick", "crew_captain"):
        name, _more = _name_and_rest(text, tokens, used)
        return {"c": meaning, "to": name}
    if meaning == "embark":
        name, _more = _name_and_rest(text, tokens, used)
        return {"c": "embark", "to": name} if name else {"c": "embark"}
    if meaning == "refuel":
        numbers = [_number(t[2]) for t in tokens[used:] if _number(t[2]) is not None]
        return {"c": "refuel", "n": numbers[0]} if numbers else {"c": "refuel"}
    if meaning in ("load", "unload"):
        item, n = _thing_and_count(tokens, used, allow_all=True)
        message = {"c": meaning, "item": item}
        if n is not None:
            message["n"] = n
        return message
    if meaning in ("talk", "greet"):
        return {"c": meaning, "to": rest}
    if meaning.startswith("partner"):
        op = {"partner": "status", "partner_ask": "ask", "partner_end": "end",
              "partner_end_confirm": "end_confirm"}[meaning]
        name = _word(text, tokens[used]) if op == "ask" and used < len(tokens) else rest
        return {"c": "partner", "op": op, "to": name}
    if meaning in ("adopt", "family"):
        return {"c": meaning}
    if meaning.startswith("child_"):
        words = rest.split()
        while words and words[0].lower() in ("untuk", "to", "for", "kepada", "ke", "pada", "buat"):
            words = words[1:]
        while words and words[-1].lower() in ("along", "serta", "ikut", "for", "help"):
            words = words[:-1]
        return {"c": "child", "op": meaning[6:], "a": " ".join(words)}
    if meaning == "naming":
        return {"c": "naming", "a": rest}
    if meaning == "propose":
        return {"c": "wedding", "op": "propose", "to": rest}
    if meaning == "wedding" or meaning.startswith("wedding_"):
        op = "status" if meaning == "wedding" else meaning[8:]
        message = {"c": "wedding", "op": op, "a": rest}
        if op in ("rsvp_yes", "rsvp_no", "cancel"):
            message["to"] = _word(text, tokens[used]).strip(_EDGE) if used < len(tokens) else ""
        return message
    if meaning == "residents":
        return {"c": "residents"}
    if meaning == "ask":
        return _ask(text, tokens, used)
    if meaning == "achievements":
        return {"c": "achievements", "to": _word(text, tokens[used]) if used < len(tokens) else ""}
    if meaning == "leaderboard":
        return {"c": "leaderboard", "a": rest}
    if meaning in ADMIN_OPS:
        return _admin(meaning, text, tokens, used)
    return None


ABOUT_WORDS = ("tentang", "soal", "mengenai", "perihal", "about", "regarding")
WEDDING_WORDS = {"pernikahan", "pernikahanku", "pernikahan kami", "wedding", "nikah", "resepsi", "pesta"}
TO_WORDS = ("ke", "pada", "kepada", "sama", "to")


def _ask(text, tokens, used):
    """ "tanya Bang Jali tentang gosip", "ask Jali about the reactor", "tanya Jali gosip"."""
    start = used
    if start < len(tokens) and tokens[start][2] in TO_WORDS:
        start += 1
    if start >= len(tokens):
        return {"c": "ask", "to": "", "a": ""}
    for i in range(start, len(tokens)):
        if tokens[i][2] in ABOUT_WORDS:
            name = text[tokens[start][0]:tokens[i - 1][1]].strip(_EDGE) if i > start else ""
            return {"c": "ask", "to": name, "a": _rest(text, tokens, i + 1)}
    return {"c": "ask", "to": _word(text, tokens[start]), "a": _rest(text, tokens, start + 1)}


def _admin(op, text, tokens, used):
    message = {"c": "admin", "op": op}
    if op in ("economy", "transfers", "admin_log", "invisible", "hunt_status", "new_season", "hunt_test"):
        return message
    if op == "release_hint":
        numbers = [_number(t[2]) for t in tokens[used:] if _number(t[2]) is not None]
        if numbers:
            message["n"] = numbers[0]
        return message
    if op in ("goto", "event_start", "event_stop", "event_schedule", "crew_disband", "duel_stop"):
        message["a"] = _rest(text, tokens, used)
        return message
    if op == "set_price":
        item, n = _thing_and_count(tokens, used)
        message["item"] = item
        if n is not None:
            message["n"] = n
        return message
    name, _more = _name_and_rest(text, tokens, used)
    message["to"] = name
    if op in ("grant", "take_credits"):
        numbers = [_number(t[2]) for t in tokens[used + 1:] if _number(t[2]) is not None]
        if numbers:
            message["n"] = numbers[0]
    elif op == "give_item":
        item, n = _thing_and_count(tokens, used + 1)
        message["item"] = item
        if n is not None:
            message["n"] = n
    return message
