# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Bahasa Indonesia for the quick reminder. Fields: DEVELOPERS.md, "For translators".

"setengah 9" is 08:30 (half BEFORE nine), "jam 8 kurang seperempat" 07:45,
"jam 8 lewat 15" 08:15. "minggu" is a week in "minggu depan" and "tiap
minggu", and Sunday elsewhere ("hari Minggu", "Minggu pagi").
"""

PACK = {
    "code": "id",
    "name": "Bahasa Indonesia",
    "date_order": "DMY",
    "numbers": {
        "nol": 0, "satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5, "enam": 6,
        "tujuh": 7, "delapan": 8, "sembilan": 9, "sepuluh": 10, "sebelas": 11,
        "dua belas": 12, "lima belas": 15, "dua puluh": 20, "tiga puluh": 30,
        "empat puluh": 40, "empat puluh lima": 45,
    },
    "count_words": [],
    "weekdays": [["senin"], ["selasa"], ["rabu"], ["kamis"], ["jumat", "jum'at"], ["sabtu"],
                 ["minggu", "ahad"]],
    "weekday_abbreviations": [["sen"], ["sel"], ["rab"], ["kam"], ["jum"], ["sab"], ["min"]],
    "months": [
        ["januari", "jan"], ["februari", "feb", "pebruari", "peb"], ["maret", "mar"],
        ["april", "apr"], ["mei"], ["juni", "jun"], ["juli", "jul"],
        ["agustus", "agu", "agt", "ags", "agus"], ["september", "sep", "sept"],
        ["oktober", "okt"], ["november", "nov", "nopember", "nop"], ["desember", "des"],
    ],
    "relative_days": {"hari ini": 0, "besok": 1, "esok": 1, "lusa": 2, "besok lusa": 2},
    "units": {
        "minute": ["menit", "mnt"], "hour": ["jam"], "day": ["hari"],
        "week": ["minggu", "pekan"], "month": ["bulan"], "year": ["tahun", "thn"],
    },
    "counted_units": {
        "semenit": ["minute", 1], "seperempat jam": ["minute", 15],
        "setengah jam": ["minute", 30], "sejam": ["hour", 1], "sehari": ["day", 1],
        "seminggu": ["week", 1], "sepekan": ["week", 1], "sebulan": ["month", 1],
        "setahun": ["year", 1],
    },
    "parts_of_day": [
        {"part": "morning", "words": ["pagi"]},
        {"part": "midday", "words": ["siang"]},
        {"part": "afternoon", "words": ["sore"]},
        {"part": "evening", "words": ["malam"]},
    ],
    "noon": ["tengah hari"],
    "midnight": ["tengah malam"],
    "meridiem_am": [],
    "meridiem_pm": [],
    "clock_prefixes": ["jam", "pukul", "pkl", "pkl.", "pk"],
    "clock_suffixes": ["wib", "wita", "wit"],
    "clock_idioms": [
        {"pattern": "setengah {h}", "minutes": -30},
        {"pattern": "{h} kurang seperempat", "minutes": -15},
        {"pattern": "{h} kurang {m} [menit]", "minutes": "-m"},
        {"pattern": "{h} (lewat|lebih) seperempat", "minutes": 15},
        {"pattern": "{h} (lewat|lebih) {m} [menit]", "minutes": "+m"},
        {"pattern": "{h} seperempat", "minutes": 15},
    ],
    "relative_patterns": ["{dur} lagi", "dalam {dur}", "{dur} dari sekarang", "{dur} kemudian"],
    "weekday_prefixes": ["hari", "pada hari", "pada"],
    "next_before": [],
    "next_after": ["depan", "mendatang", "yang akan datang"],
    "this_before": ["nanti"],
    "this_after": ["ini", "nanti"],
    "every": ["tiap", "setiap", "saban", "tiap-tiap"],
    "every_other": [],
    # Not "ulang": "ulang tahun" is a birthday.
    "repeat_leads": ["ulangi", "diulangi", "diulang", "berulang"],
    "repeat_words": {"daily": ["harian"], "weekly": ["mingguan"], "monthly": ["bulanan"],
                     "yearly": ["tahunan"]},
    "repeat_patterns": ["{dur} sekali"],
    "day_prefixes": ["tanggal", "tgl", "tgl."],
    "ordinal_day_prefixes": [],
    "ordinal_suffixes": [],
    "date_connectors": [],
    "fillers": ["pada", "pd", "nanti", "sekitar", "tepat", "dan", "untuk", "agar", "supaya",
                "ya", "yah", "eh", "deh", "dong", "sih"],
    "triggers": [
        "[tolong|coba] ingatkan [aku|saya|gue|gw|kami|kita] [untuk|buat|agar|supaya|kalau|bahwa]",
        "[tolong|coba] ingetin [aku|saya|gue|gw] [untuk|buat|kalau]",
        "[tolong|coba] (buat|buatkan|bikin|bikinin|pasang) pengingat [untuk|buat]",
        "pengingat [:]",
        "jangan lupa [untuk]",
    ],
}

# (now, sentence, expected). Thursday 24 September 2026 10:40 unless noted.
EXAMPLES = [
    ("2026-09-24 10:40", "ingatkan aku minum obat besok jam 8 pagi, ulangi tiap hari",
     {"title": "Minum obat", "date": "2026-09-25", "time": "08:00", "recurrence": "daily",
      "interval": 1}),
    ("2026-09-24 10:40", "besok setengah 9 rapat",
     {"title": "Rapat", "date": "2026-09-25", "time": "08:30"}),
    ("2026-09-24 10:40", "rapat besok jam 8 kurang seperempat",
     {"title": "Rapat", "date": "2026-09-25", "time": "07:45"}),
    ("2026-09-24 10:40", "telepon ibu 30 menit lagi",
     {"title": "Telepon ibu", "date": "2026-09-24", "time": "11:10"}),
    ("2026-09-24 10:40", "bayar listrik tiap tanggal 5",
     {"title": "Bayar listrik", "date": "2026-10-05", "time": "09:00", "recurrence": "monthly",
      "time_assumed": True}),
    ("2026-09-24 10:40", "olahraga tiap Senin jam 6 pagi",
     {"title": "Olahraga", "date": "2026-09-28", "time": "06:00", "recurrence": "weekly"}),
    ("2026-09-24 10:40", "arisan minggu depan",
     {"title": "Arisan", "date": "2026-10-01", "time": "09:00", "time_assumed": True}),
    ("2026-09-24 10:40", "nonton bola nanti malam",
     {"title": "Nonton bola", "date": "2026-09-24", "time": "19:00"}),
    ("2026-09-24 10:40", "servis motor 5 Oktober jam 10",
     {"title": "Servis motor", "date": "2026-10-05", "time": "10:00"}),
    ("2026-09-24 10:40", "minum vitamin 2 hari sekali jam 7 pagi",
     {"title": "Minum vitamin", "date": "2026-09-25", "time": "07:00", "recurrence": "daily",
      "interval": 2}),
    ("2026-09-24 10:40", "pengingat: kumpulkan tugas Senin minggu depan jam 1 siang",
     {"title": "Kumpulkan tugas", "date": "2026-09-28", "time": "13:00"}),
]
