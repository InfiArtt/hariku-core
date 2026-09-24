# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the quick reminder's sentence reader (core/when.py) and its
# language packs (core/when_packs.py, core/when_lang_*.py): every sentence in
# every pack, resolve() for a future AI fallback, and the packs themselves.
# The read-back, saving and the windows are in test_quick_reminder.py.

import ast
import datetime
import os
import re

import pytest

from core import when
from core import when_packs as packs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_DIR = os.path.join(ROOT, "core")

THU = datetime.datetime(2026, 9, 24, 10, 40)      # Thursday 24 September 2026, 10:40
EARLY = datetime.datetime(2026, 9, 24, 6, 0)
LATE = datetime.datetime(2026, 9, 24, 22, 30)
NEAR_MIDNIGHT = datetime.datetime(2026, 9, 24, 23, 50)
TUE = datetime.datetime(2026, 9, 22, 9, 0)         # Tuesday
MONTH_END = datetime.datetime(2026, 9, 30, 23, 0)  # last day of a 30-day month
OCTOBER = datetime.datetime(2026, 10, 10, 9, 0)
DECEMBER = datetime.datetime(2026, 12, 20, 10, 0)

MIXED = ["id", "en", "de"]


def parse(text, now=THU, language="id", use=None):
    return when.parse(text, now, language=language, packs=use)


# (now, UI language, sentence, expected fields). Packs: the default ones (the UI
# language, English, Indonesian) unless the case says MIXED (German too).
TABLE = [
    # --- the sentence the local models got wrong -------------------------------
    (THU, "id", "ingatkan aku minum obat besok jam 8 pagi, ulangi tiap hari",
     dict(title="Minum obat", date="2026-09-25", time="08:00", recurrence="daily", interval=1)),

    # --- titles and trigger words ----------------------------------------------
    (THU, "id", "Ingatkan saya untuk bayar listrik besok jam 10",
     dict(title="Bayar listrik", date="2026-09-25", time="10:00")),
    (THU, "id", "ingatkan gue buat telepon Budi besok jam 7 malam",
     dict(title="Telepon Budi", date="2026-09-25", time="19:00")),
    (THU, "id", "ingatkan gw ambil jahitan lusa",
     dict(title="Ambil jahitan", date="2026-09-26")),
    (THU, "id", "tolong ingatkan aku angkat jemuran besok sore",
     dict(title="Angkat jemuran", date="2026-09-25", time="16:00")),
    (THU, "id", "pengingat: rapat RT besok jam 19.30",
     dict(title="Rapat RT", date="2026-09-25", time="19:30")),
    (THU, "en", "remind me to call mom tomorrow at 7pm",
     dict(title="Call mom", date="2026-09-25", time="19:00")),
    (THU, "en", "Reminder: submit the report on Friday at 5 pm",
     dict(title="Submit the report", date="2026-09-25", time="17:00")),
    (THU, "id", "BESOK JAM 8 MINUM OBAT!!!", dict(title="MINUM OBAT", time="08:00")),
    (THU, "id", "minum obat, besok, jam 8.", dict(title="Minum obat", time="08:00")),
    (THU, "id", "minum obat besok jam 8 sesudah makan",
     dict(title="Minum obat sesudah makan", time="08:00")),
    (THU, "id", "ulang tahun ibu tiap tahun 17 Agustus",
     dict(title="Ulang tahun ibu", date="2027-08-17", recurrence="yearly")),

    # --- days --------------------------------------------------------------------
    (THU, "id", "rapat hari ini jam 3 sore", dict(date="2026-09-24", time="15:00")),
    (THU, "en", "meeting today at 3 pm", dict(date="2026-09-24", time="15:00")),
    (THU, "id", "rapat besok", dict(date="2026-09-25", time="09:00", time_assumed=True)),
    (THU, "id", "rapat esok", dict(date="2026-09-25")),
    (THU, "en", "meeting tomorrow", dict(date="2026-09-25", time_assumed=True)),
    (THU, "id", "rapat lusa", dict(date="2026-09-26")),
    (THU, "id", "rapat besok lusa", dict(date="2026-09-26")),
    (THU, "en", "meeting the day after tomorrow", dict(date="2026-09-26")),
    (THU, "id", "rapat Senin", dict(date="2026-09-28")),
    (THU, "id", "rapat hari Senin", dict(date="2026-09-28")),
    (THU, "id", "rapat pada hari Senin", dict(date="2026-09-28", title="Rapat")),
    (THU, "id", "rapat Senin depan", dict(date="2026-09-28")),
    (THU, "id", "rapat Senin minggu depan", dict(date="2026-09-28")),
    (THU, "en", "meeting next Monday", dict(date="2026-09-28")),
    (THU, "en", "meeting on Monday", dict(date="2026-09-28")),
    (THU, "en", "meeting on Mon", dict(date="2026-09-28")),
    (THU, "id", "rapat Kamis", dict(date="2026-10-01")),            # never today
    (THU, "id", "rapat Jum'at", dict(date="2026-09-25")),
    (TUE, "id", "rapat Kamis minggu depan", dict(date="2026-10-01")),  # not this Thursday
    (TUE, "en", "meeting Thursday next week", dict(date="2026-10-01")),
    (TUE, "id", "rapat Kamis", dict(date="2026-09-24")),
    (THU, "id", "rapat minggu depan", dict(date="2026-10-01", time_assumed=True)),
    (THU, "id", "rapat pekan depan", dict(date="2026-10-01")),
    (THU, "en", "meeting next week", dict(date="2026-10-01")),
    (THU, "id", "rapat bulan depan", dict(date="2026-10-24")),
    (THU, "en", "meeting next month", dict(date="2026-10-24")),
    (THU, "id", "rapat hari Minggu", dict(date="2026-09-27")),
    (THU, "id", "gereja Minggu pagi", dict(title="Gereja", date="2026-09-27", time="07:00")),
    (THU, "id", "rapat hari Minggu depan", dict(date="2026-09-27")),
    (THU, "id", "rapat 3 hari lagi", dict(date="2026-09-27")),
    (THU, "en", "dentist in 2 weeks", dict(date="2026-10-08")),

    # --- dates ---------------------------------------------------------------------
    (THU, "id", "servis motor 5 Oktober", dict(date="2026-10-05", title="Servis motor")),
    (THU, "id", "servis motor tanggal 5 Oktober", dict(date="2026-10-05")),
    (THU, "id", "bayar kos tanggal 5", dict(date="2026-10-05")),       # 5 September has passed
    (THU, "id", "bayar kos tgl 30", dict(date="2026-09-30")),
    (THU, "id", "bayar kos tgl. 1", dict(date="2026-10-01", title="Bayar kos")),
    (THU, "id", "rapat 5/10", dict(date="2026-10-05")),                # day/month
    (THU, "id", "rapat 5/10/2026 jam 9", dict(date="2026-10-05", time="09:00")),
    (THU, "id", "rapat 5-10-2026", dict(date="2026-10-05")),
    (THU, "id", "rapat 5.10.2026 jam 14.00", dict(date="2026-10-05", time="14:00")),
    (THU, "id", "rapat 5/10/26", dict(date="2026-10-05")),
    (THU, "id", "rapat 5 Okt 2026", dict(date="2026-10-05")),
    (THU, "en", "meeting October 5", dict(date="2026-10-05")),
    (THU, "en", "meeting Oct 5th", dict(date="2026-10-05")),
    (THU, "en", "meeting Oct 5th, 2027", dict(date="2027-10-05")),
    (THU, "en", "meeting on the 5th of October", dict(date="2026-10-05", title="Meeting")),
    (THU, "en", "pay bills on the 5th", dict(date="2026-10-05", title="Pay bills")),
    (THU, "id", "rapat 3 Agt", dict(date="2027-08-03")),               # August has passed
    (THU, "id", "rapat 17 Agu", dict(date="2027-08-17")),
    (THU, "id", "rapat 1 Des", dict(date="2026-12-01")),
    (THU, "id", "rapat 2 Mei", dict(date="2027-05-02")),
    (THU, "id", "rapat 12 Jan", dict(date="2027-01-12")),
    (THU, "id", "rapat 24 September", dict(date="2026-09-24")),         # today still counts
    (THU, "id", "rapat tanggal 31", dict(date="2026-10-31")),           # September has 30 days
    (MONTH_END, "id", "bayar tagihan tanggal 31", dict(date="2026-10-31")),
    (THU, "id", "ulang tahun 29 Februari", dict(date="2028-02-29")),    # the next leap year
    (DECEMBER, "id", "rapat 5 Januari", dict(date="2027-01-05")),       # year rollover
    (DECEMBER, "en", "party on 2 January", dict(date="2027-01-02")),
    (THU, "id", "rapat tanggal 5 bulan depan", dict(date="2026-10-05")),
    (THU, "id", "perpanjang SIM tahun depan tanggal 5 Januari", dict(date="2027-01-05")),

    # --- times -----------------------------------------------------------------------
    (THU, "id", "minum obat jam 8", dict(date="2026-09-24", time="20:00", date_assumed=True)),
    (LATE, "id", "minum obat jam 8", dict(date="2026-09-25", time="08:00")),
    (EARLY, "id", "minum obat jam 8", dict(date="2026-09-24", time="08:00")),
    (THU, "id", "minum obat pukul 8", dict(date="2026-09-24", time="20:00")),
    (THU, "id", "minum obat besok jam 8", dict(date="2026-09-25", time="08:00")),
    (THU, "id", "meeting besok jam 3", dict(date="2026-09-25", time="15:00")),  # daytime rule
    (THU, "id", "rapat hari ini jam 8", dict(date="2026-09-24", time="20:00")),
    (EARLY, "id", "rapat hari ini jam 8", dict(date="2026-09-24", time="08:00")),
    (THU, "id", "rapat jam 08.30", dict(date="2026-09-25", time="08:30")),     # 24-hour
    (THU, "id", "rapat 8:30", dict(date="2026-09-24", time="20:30")),
    (THU, "id", "rapat 20.00", dict(date="2026-09-24", time="20:00")),
    (THU, "id", "rapat jam 13.30", dict(date="2026-09-24", time="13:30")),
    (THU, "id", "rapat jam 10.40", dict(date="2026-09-24", time="22:40")),     # now has passed
    (THU, "id", "rapat 8 pagi", dict(date="2026-09-25", time="08:00")),
    (THU, "id", "rapat jam delapan pagi", dict(date="2026-09-25", time="08:00")),
    (THU, "id", "rapat jam 8 malam", dict(date="2026-09-24", time="20:00")),
    (LATE, "id", "rapat jam 8 malam", dict(date="2026-09-25", time="20:00")),
    (THU, "id", "rapat 8 pm", dict(time="20:00")),
    (THU, "en", "meeting at 8 am", dict(date="2026-09-25", time="08:00")),
    (THU, "en", "meeting tomorrow at 12 am", dict(date="2026-09-25", time="00:00")),
    (THU, "en", "meeting tomorrow at 12 pm", dict(date="2026-09-25", time="12:00")),
    (THU, "id", "rapat jam 1 siang", dict(date="2026-09-24", time="13:00")),
    (THU, "id", "rapat jam 11 siang", dict(date="2026-09-24", time="11:00")),
    (THU, "id", "rapat jam 12 siang", dict(date="2026-09-24", time="12:00")),
    (THU, "id", "rapat jam 4 sore", dict(date="2026-09-24", time="16:00")),
    (THU, "id", "rapat jam 9 malam", dict(date="2026-09-24", time="21:00")),
    (THU, "id", "rapat jam 12 malam", dict(date="2026-09-25", time="00:00")),
    (THU, "id", "rapat besok jam 12 malam", dict(date="2026-09-26", time="00:00")),
    (THU, "id", "ronda jam 2 malam", dict(date="2026-09-25", time="02:00")),
    (THU, "id", "rapat jam 9 malam ini", dict(date="2026-09-24", time="21:00", title="Rapat")),
    (THU, "id", "rapat tengah malam", dict(date="2026-09-25", time="00:00")),
    (THU, "en", "lunch at noon tomorrow", dict(date="2026-09-25", time="12:00")),
    (THU, "id", "rapat pukul 9 WIB besok", dict(date="2026-09-25", time="09:00")),
    # half and quarter idioms
    (THU, "id", "rapat besok setengah 9", dict(date="2026-09-25", time="08:30")),
    (THU, "id", "rapat besok jam setengah 9", dict(time="08:30")),
    (THU, "id", "rapat setengah 9", dict(date="2026-09-24", time="20:30")),  # half BEFORE nine
    (THU, "id", "rapat setengah 1 siang", dict(date="2026-09-24", time="12:30")),
    (THU, "id", "rapat besok jam 8 kurang seperempat", dict(time="07:45")),
    (THU, "id", "rapat besok jam 8 kurang 10", dict(time="07:50")),
    (THU, "id", "rapat besok jam 8 lewat 15", dict(time="08:15")),
    (THU, "id", "rapat besok jam 8 lebih 15 menit", dict(time="08:15")),
    (THU, "id", "rapat besok jam 8 seperempat", dict(time="08:15")),
    (THU, "id", "rapat besok jam 8 lewat seperempat", dict(time="08:15")),
    (THU, "en", "meeting tomorrow at half past eight", dict(time="08:30")),   # half AFTER
    (THU, "en", "meeting tomorrow at a quarter to nine", dict(time="08:45")),
    (THU, "en", "meeting tomorrow at 10 past 8", dict(time="08:10")),
    (THU, "en", "meeting tomorrow at 20 to 9", dict(time="08:40")),
    (THU, "en", "meeting tomorrow at eight thirty", dict(time="08:30")),
    # relative times
    (THU, "id", "telepon ibu 30 menit lagi", dict(date="2026-09-24", time="11:10")),
    (THU, "id", "angkat jemuran 2 jam lagi", dict(time="12:40")),
    (THU, "id", "masak nasi dalam 15 menit", dict(time="10:55")),
    (THU, "id", "cek oven setengah jam lagi", dict(time="11:10")),
    (THU, "id", "masak sejam lagi", dict(time="11:40")),
    (THU, "en", "check the oven in 10 minutes", dict(time="10:50", title="Check the oven")),
    (THU, "en", "stretch in an hour", dict(time="11:40")),
    (THU, "en", "tea in half an hour", dict(time="11:10")),
    (NEAR_MIDNIGHT, "id", "matikan kompor 30 menit lagi", dict(date="2026-09-25", time="00:20")),
    # parts of the day without a clock time
    (THU, "id", "rapat besok pagi", dict(date="2026-09-25", time="07:00")),
    (THU, "id", "rapat besok siang", dict(date="2026-09-25", time="12:00")),
    (THU, "id", "rapat besok sore", dict(date="2026-09-25", time="16:00")),
    (THU, "id", "rapat besok malam", dict(date="2026-09-25", time="19:00")),
    (THU, "id", "nonton bola nanti malam", dict(date="2026-09-24", time="19:00")),
    (THU, "id", "rapat nanti sore", dict(date="2026-09-24", time="16:00")),
    (THU, "id", "rapat malam ini", dict(date="2026-09-24", time="19:00")),
    (THU, "id", "rapat pagi", dict(date="2026-09-25", time="07:00")),       # 07:00 has passed
    (THU, "id", "rapat sore", dict(date="2026-09-24", time="16:00")),
    (THU, "en", "water the plants tonight", dict(date="2026-09-24", time="19:00")),
    (THU, "en", "call Budi tomorrow afternoon", dict(time="15:00")),        # the pack's default
    (THU, "id", "rapat nanti malam jam 9", dict(date="2026-09-24", time="21:00")),
    # no time at all
    (THU, "id", "rapat Senin", dict(time="09:00", time_assumed=True)),

    # --- repeats -------------------------------------------------------------------------
    (THU, "id", "minum obat tiap hari", dict(recurrence="daily", interval=1, time="09:00",
                                            date="2026-09-25", time_assumed=True)),
    (THU, "id", "minum obat setiap hari jam 7 malam", dict(recurrence="daily", date="2026-09-24",
                                                        time="19:00")),
    (THU, "id", "minum obat tiap hari jam 8", dict(recurrence="daily", date="2026-09-25",
                                                 time="08:00")),   # repeats: daytime rule
    (THU, "en", "take pills daily at 9 pm", dict(recurrence="daily", time="21:00")),
    (THU, "en", "take pills every day", dict(recurrence="daily")),
    (THU, "id", "ulangi tiap hari minum obat jam 7 pagi", dict(title="Minum obat",
                                                             recurrence="daily", time="07:00")),
    (THU, "id", "senam tiap Senin", dict(recurrence="weekly", date="2026-09-28")),
    (THU, "id", "senam setiap hari Senin jam 6 pagi", dict(recurrence="weekly",
                                                         date="2026-09-28", time="06:00")),
    (THU, "id", "misa tiap hari Minggu pagi", dict(recurrence="weekly", date="2026-09-27",
                                                 time="07:00", title="Misa")),
    (THU, "en", "gym every Monday", dict(recurrence="weekly", date="2026-09-28")),
    (THU, "en", "gym mondays at 6 pm", dict(recurrence="weekly", date="2026-09-28",
                                            time="18:00")),
    (THU, "id", "arisan tiap minggu", dict(recurrence="weekly", interval=1)),   # a week, not Sunday
    (THU, "en", "clean up weekly", dict(recurrence="weekly")),
    (THU, "id", "bayar listrik tiap bulan tanggal 5", dict(recurrence="monthly",
                                                         date="2026-10-05")),
    (THU, "id", "bayar listrik setiap tanggal 25", dict(recurrence="monthly", date="2026-09-25")),
    (THU, "id", "arisan tiap bulan", dict(recurrence="monthly")),
    (THU, "en", "pay rent monthly on the 1st", dict(recurrence="monthly", date="2026-10-01")),
    (THU, "id", "bayar pajak tiap tahun", dict(recurrence="yearly")),
    (THU, "en", "renew insurance yearly on 1 March", dict(recurrence="yearly",
                                                        date="2027-03-01")),
    (THU, "id", "minum vitamin tiap 2 hari", dict(recurrence="daily", interval=2)),
    (THU, "id", "minum vitamin setiap dua hari", dict(recurrence="daily", interval=2)),
    (THU, "en", "water plants every 2 days", dict(recurrence="daily", interval=2)),
    (THU, "en", "water plants every other day", dict(recurrence="daily", interval=2)),
    (THU, "id", "ganti sprei tiap 3 minggu", dict(recurrence="weekly", interval=3)),
    (THU, "id", "cuci AC 2 bulan sekali", dict(recurrence="monthly", interval=2, title="Cuci AC")),
    (THU, "id", "minum obat sehari sekali jam 7 malam", dict(recurrence="daily", time="19:00")),
    (THU, "en", "vitamins once a day", dict(recurrence="daily")),

    # --- mixed languages -------------------------------------------------------------------
    (THU, "en", "call Mama tomorrow jam 7 malam", dict(title="Call Mama", date="2026-09-25",
                                                      time="19:00", packs=["en", "id"])),
    (THU, "id", "meeting besok jam 3", dict(title="Meeting", packs=["id"])),
    (THU, "id", "rapat tomorrow at 5 pm", dict(title="Rapat", date="2026-09-25",
                                                time="17:00", packs=["en"])),
    (THU, "en", "ingatkan aku rapat sore", dict(title="Rapat", time="16:00", packs=["id"])),
]


def _case_id(case):
    now, language, text, _expected = case
    return f"{now:%m%d-%H%M}-{language}-{text[:40]}"


@pytest.mark.parametrize("case", TABLE, ids=[_case_id(c) for c in TABLE])
def test_sentence(case):
    now, language, text, expected = case
    result = parse(text, now, language)
    got = {key: getattr(result, key) for key in expected}
    assert got == expected, result
    assert result.ok, result


# German needs its pack switched on in Preferences, Reminders.
GERMAN = [
    ("morgen um 8 Uhr Zahnarzt", dict(title="Zahnarzt", date="2026-09-25", time="08:00")),
    ("übermorgen Mutter anrufen", dict(date="2026-09-26", time_assumed=True)),
    ("nächsten Montag Besprechung", dict(date="2026-09-28")),
    ("am Montag Besprechung", dict(date="2026-09-28")),
    ("am 5. Oktober Reifen wechseln", dict(date="2026-10-05")),
    ("jeden Tag Tabletten", dict(recurrence="daily")),
    ("jeden Montag Sport", dict(recurrence="weekly", date="2026-09-28")),
    ("alle 2 Tage Blumen gießen", dict(recurrence="daily", interval=2)),
    ("in 30 Minuten Nudeln", dict(time="11:10")),
    ("heute Abend Müll", dict(date="2026-09-24", time="19:00")),
    ("morgen halb neun Bus", dict(time="08:30")),                 # half BEFORE nine
    ("morgen Viertel vor acht Bus", dict(time="07:45")),
    ("morgen Viertel nach acht Bus", dict(time="08:15")),
    ("morgen um 3 Uhr nachmittags Arzt", dict(time="15:00")),
    ("erinnere mich an den Termin morgen um 10", dict(title="Den Termin", time="10:00")),
    ("erinnere mich, morgen die Tabletten zu nehmen", dict(title="Die Tabletten nehmen")),
]


@pytest.mark.parametrize("text, expected", GERMAN, ids=[g[0] for g in GERMAN])
def test_german_when_switched_on(text, expected):
    result = parse(text, THU, "en", use=packs.default_codes("en", ["de"]))
    got = {key: getattr(result, key) for key in expected}
    assert got == expected, result
    assert "de" in result.packs


def test_german_is_off_by_default():
    result = parse("übermorgen Mutter anrufen", THU, "id")
    assert "nothing_found" in result.problems


# --- warnings, problems and the fallback hook ------------------------------------------

def test_nothing_found():
    result = parse("minum obat")
    assert result.problems == ["nothing_found"]
    assert (result.date, result.time) == (None, None)
    assert not result.ok and result.needs_fallback and result.confidence == 0.0


def test_no_title():
    result = parse("besok jam 8")
    assert "no_title" in result.problems and not result.ok
    assert (result.date, result.time) == ("2026-09-25", "08:00")


def test_time_assumed_on_today_can_be_in_the_past():
    result = parse("rapat hari ini")
    assert (result.date, result.time) == ("2026-09-24", "09:00")
    assert result.time_assumed and result.in_past and result.ok


def test_tonight_after_the_evening_default_is_in_the_past():
    result = parse("rapat nanti malam", LATE)
    assert (result.date, result.time, result.in_past) == ("2026-09-24", "19:00", True)


def test_explicit_past_date():
    result = parse("rapat 5 Oktober 2020 jam 9")
    assert result.date == "2020-10-05" and result.in_past


@pytest.mark.parametrize("text", ["rapat 29 Februari 2027", "rapat 31/9", "rapat 31 September 2026",
                                  "rapat 0/10"])
def test_dates_that_do_not_exist(text):
    result = parse(text)
    assert "invalid_date" in result.problems or "nothing_found" in result.problems
    assert not result.ok


def test_day_that_next_month_lacks():
    result = parse("rapat tanggal 31 bulan depan", OCTOBER)    # November has 30 days
    assert result.problems == ["invalid_date"] and not result.ok


@pytest.mark.parametrize("text", ["stretch every hour", "minum obat tiap jam",
                                  "cek tiap 10 menit"])
def test_repeats_the_core_cannot_do(text):
    assert "unsupported_repeat" in parse(text, language="en").problems


def test_two_times_keep_the_first_and_warn():
    result = parse("rapat jam 8 pagi, eh jam 9 pagi")
    assert result.time == "08:00" and "conflict" in result.problems and result.ok
    assert result.title == "Rapat"


def test_two_dates_warn():
    result = parse("rapat besok hari ini")
    assert "conflict" in result.problems


def test_weekday_beats_tomorrow_when_they_disagree():
    result = parse("rapat besok Senin")
    assert result.date == "2026-09-28" and "conflict" in result.problems


def test_tomorrow_and_its_weekday_agree():
    result = parse("rapat besok Jumat jam 9")
    assert result.date == "2026-09-25" and result.problems == []


def test_clean_sentence_is_confident():
    result = parse("ingatkan aku minum obat besok jam 8 pagi, ulangi tiap hari")
    assert result.confidence == 1.0 and not result.needs_fallback
    assert result.recognised == ["besok", "jam 8 pagi", "ulangi tiap hari"]
    assert result.trigger == "ingatkan aku"
    assert result.leftover == ["minum", "obat"] and result.unparsed == []
    assert result.packs == ["id"]


def test_unparsed_words_lower_confidence():
    result = parse("minum obat jam 25")
    assert "jam" in result.unparsed and "25" in result.unparsed
    assert result.needs_fallback


def test_a_week_day_list_is_left_for_the_fallback():
    result = parse("standup every weekday", language="en")
    assert "every" in result.unparsed and result.needs_fallback


def test_birthday_words_are_not_flagged():
    result = parse("ulang tahun ibu besok")
    assert result.title == "Ulang tahun ibu" and result.unparsed == []


def test_everyday_words_that_look_like_a_part_of_the_day():
    # "sore" is Indonesian afternoon and English for painful.
    result = parse("take medicine for sore throat tomorrow at 8", language="en")
    assert result.title == "Take medicine for sore throat"
    assert (result.date, result.time) == ("2026-09-25", "08:00")
    assert result.unparsed == ["sore"] and result.needs_fallback
    # Alone and in Indonesian, it is the afternoon ...
    assert parse("rapat sore", language="id").time == "16:00"
    # ... but not when Hariku is in English and nothing else is Indonesian.
    assert "nothing_found" in parse("rapat sore", language="en").problems


def test_german_am_before_a_weekday_is_not_a_m():
    result = parse("um 3 am Montag Arzt", THU, "en", use=["en", "id", "de"])
    assert (result.date, result.time) == ("2026-09-28", "15:00")
    assert parse("meeting at 3 am", language="en").time == "03:00"


def test_jam_is_a_clock_word_and_a_unit():
    assert parse("rapat jam 2").time == "14:00"
    assert parse("rapat 2 jam lagi").time == "12:40"


def test_packs_matched_in_priority_order():
    assert parse("call Mama tomorrow jam 7 malam", language="id").packs == ["id", "en"]
    assert parse("call Mama tomorrow jam 7 malam", language="en").packs == ["en", "id"]
    assert parse("rapat 8:30").packs == []


@pytest.mark.parametrize("text", [
    "", "   ", ",,, !!", "::::", "//", "8.", "jam", "tanggal", "5/", "99/99/9999", "jam 8 kurang",
    "setengah", "every", "tiap", "٨ pagi", "rapat 🎉 besok", "a" * 500, "1 2 3 4 5 6 7 8 9",
    "jam 8 jam 8 jam 8", "remind me to", "ingatkan aku", "tanggal 99", "5.10.", "am 5.10.",
])
def test_odd_input_never_raises(text):
    result = parse(text, language="en", use=MIXED)
    assert isinstance(result.problems, list)


def test_trigger_only_before_the_title():
    result = parse("minum obat ingatkan aku besok")
    assert result.title == "Minum obat ingatkan aku"


def test_to_dict_has_the_fields_a_fallback_needs():
    data = parse("minum obat besok jam 8").to_dict()
    for key in ("title", "date", "time", "recurrence", "interval", "recognised", "leftover",
                "unparsed", "time_assumed", "date_assumed", "problems", "confidence", "packs",
                "ok"):
        assert key in data


# --- resolve(): the neutral structure a future AI fallback will produce ------------------

@pytest.mark.parametrize("components, expected", [
    (dict(title="minum obat", day_offset=1, hour=8, part_of_day="morning", recurrence="daily"),
     dict(title="Minum obat", date="2026-09-25", time="08:00", recurrence="daily")),
    (dict(title="rapat", weekday=0, hour=3), dict(date="2026-09-28", time="15:00")),
    (dict(title="rapat", weekday=3, week_offset=1), dict(date="2026-10-01", time="09:00",
                                                        time_assumed=True)),
    (dict(title="ulang tahun", day_of_month=29, month=2), dict(date="2028-02-29")),
    (dict(title="teh", minutes_from_now=30), dict(date="2026-09-24", time="11:10")),
    (dict(title="rapat", hour=8), dict(date="2026-09-24", time="20:00")),
    (dict(title="rapat", hour=12, part_of_day="evening"), dict(date="2026-09-25", time="00:00")),
    (dict(title="rapat", hour=8, meridiem="pm", day_offset=0), dict(time="20:00")),
    (dict(title="rapat", hour="8", minute="30", day_offset="1"), dict(time="08:30")),
    (dict(title="bayar", day_of_month=5, recurrence="monthly", interval=2),
     dict(date="2026-10-05", recurrence="monthly", interval=2)),
    (dict(title="rapat", part_of_day="afternoon", day_offset=1), dict(time="16:00")),
    (dict(title="rapat", month_offset=1, day_of_month=31), dict(date="2026-10-31")),
])
def test_resolve_components(components, expected):
    result = when.resolve(components, THU)
    got = {key: getattr(result, key) for key in expected}
    assert got == expected, result


@pytest.mark.parametrize("components, problem", [
    (dict(title="x", hour=25), "invalid_time"),
    (dict(title="x", hour="25"), "invalid_time"),
    (dict(title="x", minute=75, hour=8), "invalid_time"),
    (dict(title="x", day_of_month=31, month=9, year=2026), "invalid_date"),
    (dict(title="x", month=13, day_of_month=1), "invalid_date"),
    (dict(title="x", day_offset=1, recurrence="hourly"), "unsupported_repeat"),
    (dict(title="x"), "nothing_found"),
    (dict(day_offset=1), "no_title"),
    ("tomorrow at 8", "nothing_found"),
    (dict(title="x", hour=True), "nothing_found"),          # a bool is not an hour
])
def test_resolve_rejects_bad_components(components, problem):
    result = when.resolve(components, THU)
    assert problem in result.problems and not result.ok


def test_resolve_documents_every_field():
    for field in when._RANGES:
        assert field in when.COMPONENT_FIELDS
    for field in ("title", "hour_24", "meridiem", "part_of_day", "recurrence"):
        assert field in when.COMPONENT_FIELDS


def test_parse_hands_resolve_the_same_structure():
    result = parse("minum obat besok jam 8 pagi, tiap hari")
    again = when.resolve(result.components, THU)
    assert (again.title, again.date, again.time, again.recurrence) == \
        (result.title, result.date, result.time, result.recurrence)
    assert result.components["day_offset"] == 1 and result.components["part_of_day"] == "morning"


# --- default_date: the reminder dialog's own date ------------------------------------------

OCT5 = datetime.date(2026, 10, 5)


@pytest.mark.parametrize("text, expected", [
    ("rapat jam 3", dict(date="2026-10-05", time="15:00", date_assumed=True)),   # daytime rule
    ("rapat jam 8", dict(date="2026-10-05", time="08:00")),
    ("rapat sore", dict(date="2026-10-05", time="16:00")),
    ("minum obat tiap hari jam 8", dict(date="2026-10-05", time="08:00", recurrence="daily")),
    ("arisan tiap bulan", dict(date="2026-10-05", time="09:00", recurrence="monthly",
                               time_assumed=True)),
    ("rapat besok jam 3", dict(date="2026-09-25", time="15:00", date_assumed=False)),
    ("rapat Senin", dict(date="2026-09-28")),
    ("telepon ibu 30 menit lagi", dict(date="2026-09-24", time="11:10")),
])
def test_default_date_fills_a_sentence_without_a_date(text, expected):
    result = when.parse(text, THU, language="id", default_date=OCT5)
    got = {key: getattr(result, key) for key in expected}
    assert got == expected, result
    assert result.ok


def test_default_date_does_not_invent_a_time():
    result = when.parse("dokter gigi", THU, language="id", default_date=OCT5)
    assert result.problems == ["nothing_found"] and (result.date, result.time) == (None, None)


def test_default_date_in_resolve():
    assert when.resolve(dict(title="x", hour=8), THU, default_date=OCT5).date == "2026-10-05"
    as_datetime = datetime.datetime(2026, 10, 5, 12, 0)
    assert when.resolve(dict(title="x", hour=8), THU, default_date=as_datetime).time == "08:00"
    # Anything else is ignored: the next 8 o'clock, as without it.
    ignored = when.resolve(dict(title="x", hour=8), THU, default_date="2026-10-05")
    assert (ignored.date, ignored.time) == ("2026-09-24", "20:00")


# --- the language packs ---------------------------------------------------------------------

def test_every_pack_file_is_imported_by_name():
    # The compiled Hariku only contains the modules the core imports by name,
    # so a pack file that when_packs.py doesn't import would be missing there.
    files = sorted(name[len(packs.PACK_PREFIX):-3] for name in os.listdir(CORE_DIR)
                   if name.startswith(packs.PACK_PREFIX) and name.endswith(".py"))
    assert files == packs.available_codes()
    with open(os.path.join(CORE_DIR, "when_packs.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    imported = {alias.name for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module == "core"
                for alias in node.names}
    assert {packs.PACK_PREFIX + code for code in files} <= imported
    assert sorted(m.PACK["code"] for m in packs.PACK_MODULES) == files


def test_packs_are_found():
    assert {"id", "en", "de"} <= set(packs.available_codes())
    assert packs.default_codes("id") == ["id", "en"]
    assert packs.default_codes("en", ["de"]) == ["en", "id", "de"]
    assert packs.default_codes("fr") == ["en", "id"]
    assert packs.default_codes("en", ["xx", "de", "de"]) == ["en", "id", "de"]
    assert packs.optional_codes("id") == [c for c in packs.available_codes() if c not in ("id", "en")]
    assert packs.load_pack("xx") is None and packs.pack_examples("xx") == []
    assert packs.pack_name("de") == "Deutsch" and packs.pack_name("xx") == "xx"
    assert packs.is_clock("07:00") and not packs.is_clock("7:0") and not packs.is_clock(None)


@pytest.mark.parametrize("code", packs.available_codes())
def test_pack_is_valid(code):
    pack = packs.load_pack(code)
    assert pack["code"] == code
    assert packs.validate_pack(pack) == []
    lex = when.Lexicon([pack])               # every pattern compiles
    assert lex.codes == (code,)
    assert len(packs.pack_examples(code)) >= 5, "each pack ships at least five examples"


PACK_EXAMPLES = [(code, now, text, expected) for code in packs.available_codes()
                 for now, text, expected in packs.pack_examples(code)]


@pytest.mark.parametrize("code, now, text, expected", PACK_EXAMPLES,
                         ids=[f"{c}-{t[:40]}" for c, _n, t, _e in PACK_EXAMPLES])
def test_pack_examples(code, now, text, expected):
    result = when.parse(text, datetime.datetime.strptime(now, "%Y-%m-%d %H:%M"), packs=[code])
    got = {key: getattr(result, key) for key in expected}
    assert got == expected, result
    assert result.ok and result.packs == [code]


def test_validate_pack_reports_problems():
    assert packs.validate_pack("nope") == ["PACK is not a dict"]
    bad = {"code": "xx", "name": "X", "weekdays": [["a"]] * 6, "months": [["m"]] * 12,
           "numbers": {"one": 1}, "date_order": "YMD", "units": {"fortnight": ["f"]},
           "parts_of_day": [{"part": "dusk", "words": ["d"]}],
           "clock_idioms": [{"pattern": "half {h}"}], "fillers": "at"}
    problems = " ".join(packs.validate_pack(bad))
    for fragment in ("weekdays", "date_order", "numbers must cover", "units", "parts_of_day",
                     "clock_idioms", "fillers"):
        assert fragment in problems


@pytest.mark.parametrize("pattern", ["(a|b", "a]", "{nope}", "{h", "()", ""])
def test_bad_patterns_are_refused(pattern):
    with pytest.raises(when.PackError):
        when.compile_pattern(pattern, when.PACK_SLOTS)


def test_idiom_without_an_hour_is_refused():
    pack = dict(packs.load_pack("en"), code="xx", clock_idioms=[{"pattern": "half past",
                                                                 "minutes": 30}])
    with pytest.raises(when.PackError):
        when.Lexicon([pack])


def test_pattern_syntax():
    seq = when.compile_pattern("[tolong] ingatkan (aku|saya) {dur:x}", when.KNOWN_SLOTS)
    assert len(seq) == 4
    tokens = when.tokenize("Jum'at, 08.30 5/10 a.m.")
    assert [t.kind for t in tokens][:4] == ["word", "punct", "num", "mark"]
    assert tokens[0].norm == "jum'at"


def _string_constants(path):
    """String literals in a module, except docstrings."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body \
                and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
            docstrings.add(id(node.body[0].value))
    return {n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings}


def _pack_words(value):
    """Every word in a pack field, patterns included ({slots} left out)."""
    if isinstance(value, str):
        yield from re.findall(r"[^\W\d_]+", re.sub(r"\{[^}]*\}", " ", value).casefold())
    elif isinstance(value, list):
        for item in value:
            yield from _pack_words(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in ("part", "hours", "default", "minutes"):
                yield from _pack_words(item)


def test_engine_has_no_words_of_any_language():
    # Canonical names the engine and packs share on purpose, and the pack's
    # field names (the engine reads pack["every"], entry["minutes"]...).
    shared = set(packs.UNITS) | set(packs.PARTS) | set(packs.REPEATS) | {"am", "pm", "none"}
    shared |= {"part", "words", "hours", "default", "pattern", "minutes"}
    words = set()
    for code in packs.available_codes():
        pack = packs.load_pack(code)
        shared |= {w for key in pack for w in key.split("_")} | set(pack)
        for field, value in pack.items():
            if field in ("code", "name", "date_order"):
                continue
            words.update(_pack_words(value))
            if field in ("numbers", "relative_days", "counted_units"):
                words.update(_pack_words(list(value)))
    words = {w for w in words if len(w) > 1} - shared
    assert {"besok", "tomorrow", "morgen", "setengah", "halb", "kurang", "past"} <= words
    constants = {c.casefold() for c in _string_constants(os.path.join(CORE_DIR, "when.py"))}
    assert not (constants & words), sorted(constants & words)
