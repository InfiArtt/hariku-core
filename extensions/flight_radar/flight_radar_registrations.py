# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Aircraft registration prefixes (ICAO nationality marks) and the country or
territory each belongs to, named in English and Indonesian.

The prefix allocations follow ICAO, as compiled on Wikipedia's "List of aircraft
registration prefixes" (September 2026). Prefixes that aren't used for civil
aircraft in practice (military-only, UAV and ultralight series) are left out, so
an unknown registration is simply called a registration, never a wrong country.
"""

import re

# Country or territory -> (English, Indonesian).
COUNTRIES = {
    "AF": ("Afghanistan", "Afganistan"),
    "AL": ("Albania", "Albania"),
    "DZ": ("Algeria", "Aljazair"),
    "AD": ("Andorra", "Andorra"),
    "AO": ("Angola", "Angola"),
    "AI": ("Anguilla", "Anguilla"),
    "AG": ("Antigua and Barbuda", "Antigua dan Barbuda"),
    "AR": ("Argentina", "Argentina"),
    "AM": ("Armenia", "Armenia"),
    "AW": ("Aruba", "Aruba"),
    "AU": ("Australia", "Australia"),
    "AT": ("Austria", "Austria"),
    "AZ": ("Azerbaijan", "Azerbaijan"),
    "BS": ("Bahamas", "Bahama"),
    "BH": ("Bahrain", "Bahrain"),
    "BD": ("Bangladesh", "Bangladesh"),
    "BB": ("Barbados", "Barbados"),
    "BY": ("Belarus", "Belarus"),
    "BE": ("Belgium", "Belgia"),
    "BZ": ("Belize", "Belize"),
    "BJ": ("Benin", "Benin"),
    "BM": ("Bermuda", "Bermuda"),
    "BT": ("Bhutan", "Bhutan"),
    "BO": ("Bolivia", "Bolivia"),
    "BA": ("Bosnia and Herzegovina", "Bosnia dan Herzegovina"),
    "BW": ("Botswana", "Botswana"),
    "BR": ("Brazil", "Brasil"),
    "VG": ("British Virgin Islands", "Kepulauan Virgin Britania Raya"),
    "BN": ("Brunei", "Brunei"),
    "BG": ("Bulgaria", "Bulgaria"),
    "BF": ("Burkina Faso", "Burkina Faso"),
    "BI": ("Burundi", "Burundi"),
    "KH": ("Cambodia", "Kamboja"),
    "CM": ("Cameroon", "Kamerun"),
    "CA": ("Canada", "Kanada"),
    "CV": ("Cape Verde", "Tanjung Verde"),
    "KY": ("Cayman Islands", "Kepulauan Cayman"),
    "CF": ("Central African Republic", "Republik Afrika Tengah"),
    "TD": ("Chad", "Chad"),
    "CL": ("Chile", "Cile"),
    "CN": ("China", "Tiongkok"),
    "CO": ("Colombia", "Kolombia"),
    "KM": ("Comoros", "Komoro"),
    "CG": ("Republic of the Congo", "Republik Kongo"),
    "CD": ("Democratic Republic of the Congo", "Republik Demokratik Kongo"),
    "CK": ("Cook Islands", "Kepulauan Cook"),
    "CR": ("Costa Rica", "Kosta Rika"),
    "HR": ("Croatia", "Kroasia"),
    "CU": ("Cuba", "Kuba"),
    "CY": ("Cyprus", "Siprus"),
    "CZ": ("Czech Republic", "Ceko"),
    "DK": ("Denmark", "Denmark"),
    "DJ": ("Djibouti", "Jibuti"),
    "DM": ("Dominica", "Dominika"),
    "DO": ("Dominican Republic", "Republik Dominika"),
    "TL": ("Timor-Leste", "Timor Leste"),
    "EC": ("Ecuador", "Ekuador"),
    "EG": ("Egypt", "Mesir"),
    "SV": ("El Salvador", "El Salvador"),
    "GQ": ("Equatorial Guinea", "Guinea Khatulistiwa"),
    "ER": ("Eritrea", "Eritrea"),
    "EE": ("Estonia", "Estonia"),
    "SZ": ("Eswatini", "Eswatini"),
    "ET": ("Ethiopia", "Etiopia"),
    "FK": ("Falkland Islands", "Kepulauan Falkland"),
    "FJ": ("Fiji", "Fiji"),
    "FI": ("Finland", "Finlandia"),
    "FR": ("France", "Prancis"),
    "FR_OVERSEAS": ("French overseas territory", "wilayah seberang laut Prancis"),
    "GA": ("Gabon", "Gabon"),
    "GM": ("Gambia", "Gambia"),
    "GE": ("Georgia", "Georgia"),
    "DE": ("Germany", "Jerman"),
    "GH": ("Ghana", "Ghana"),
    "GI": ("Gibraltar", "Gibraltar"),
    "GR": ("Greece", "Yunani"),
    "GD": ("Grenada", "Grenada"),
    "GT": ("Guatemala", "Guatemala"),
    "GG": ("Guernsey", "Guernsey"),
    "GN": ("Guinea", "Guinea"),
    "GW": ("Guinea-Bissau", "Guinea-Bissau"),
    "GY": ("Guyana", "Guyana"),
    "HT": ("Haiti", "Haiti"),
    "HN": ("Honduras", "Honduras"),
    "HK": ("Hong Kong", "Hong Kong"),
    "HU": ("Hungary", "Hungaria"),
    "IS": ("Iceland", "Islandia"),
    "IN": ("India", "India"),
    "ID": ("Indonesia", "Indonesia"),
    "IR": ("Iran", "Iran"),
    "IQ": ("Iraq", "Irak"),
    "IE": ("Ireland", "Irlandia"),
    "IM": ("Isle of Man", "Pulau Man"),
    "IL": ("Israel", "Israel"),
    "IT": ("Italy", "Italia"),
    "CI": ("Ivory Coast", "Pantai Gading"),
    "JM": ("Jamaica", "Jamaika"),
    "JP": ("Japan", "Jepang"),
    "JO": ("Jordan", "Yordania"),
    "KZ": ("Kazakhstan", "Kazakhstan"),
    "KE": ("Kenya", "Kenya"),
    "KI": ("Kiribati", "Kiribati"),
    "XK": ("Kosovo", "Kosovo"),
    "KW": ("Kuwait", "Kuwait"),
    "KG": ("Kyrgyzstan", "Kirgizstan"),
    "LA": ("Laos", "Laos"),
    "LV": ("Latvia", "Latvia"),
    "LB": ("Lebanon", "Lebanon"),
    "LS": ("Lesotho", "Lesotho"),
    "LR": ("Liberia", "Liberia"),
    "LY": ("Libya", "Libya"),
    "LT": ("Lithuania", "Lituania"),
    "LU": ("Luxembourg", "Luksemburg"),
    "MO": ("Macau", "Makau"),
    "MG": ("Madagascar", "Madagaskar"),
    "MW": ("Malawi", "Malawi"),
    "MY": ("Malaysia", "Malaysia"),
    "MV": ("Maldives", "Maladewa"),
    "ML": ("Mali", "Mali"),
    "MT": ("Malta", "Malta"),
    "MH": ("Marshall Islands", "Kepulauan Marshall"),
    "MR": ("Mauritania", "Mauritania"),
    "MU": ("Mauritius", "Mauritius"),
    "MX": ("Mexico", "Meksiko"),
    "FM": ("Micronesia", "Mikronesia"),
    "MD": ("Moldova", "Moldova"),
    "MC": ("Monaco", "Monako"),
    "MN": ("Mongolia", "Mongolia"),
    "ME": ("Montenegro", "Montenegro"),
    "MS": ("Montserrat", "Montserrat"),
    "MA": ("Morocco", "Maroko"),
    "MZ": ("Mozambique", "Mozambik"),
    "MM": ("Myanmar", "Myanmar"),
    "NA": ("Namibia", "Namibia"),
    "NR": ("Nauru", "Nauru"),
    "NP": ("Nepal", "Nepal"),
    "NL": ("Netherlands", "Belanda"),
    "NL_CARIBBEAN": ("Dutch Caribbean", "Karibia Belanda"),
    "NZ": ("New Zealand", "Selandia Baru"),
    "NI": ("Nicaragua", "Nikaragua"),
    "NE": ("Niger", "Niger"),
    "NG": ("Nigeria", "Nigeria"),
    "KP": ("North Korea", "Korea Utara"),
    "MK": ("North Macedonia", "Makedonia Utara"),
    "NO": ("Norway", "Norwegia"),
    "OM": ("Oman", "Oman"),
    "PK": ("Pakistan", "Pakistan"),
    "PA": ("Panama", "Panama"),
    "PG": ("Papua New Guinea", "Papua Nugini"),
    "PY": ("Paraguay", "Paraguay"),
    "PE": ("Peru", "Peru"),
    "PH": ("Philippines", "Filipina"),
    "PL": ("Poland", "Polandia"),
    "PT": ("Portugal", "Portugal"),
    "QA": ("Qatar", "Qatar"),
    "RO": ("Romania", "Rumania"),
    "RU": ("Russia", "Rusia"),
    "RW": ("Rwanda", "Rwanda"),
    "SH": ("Saint Helena", "Saint Helena"),
    "KN": ("Saint Kitts and Nevis", "Saint Kitts dan Nevis"),
    "LC": ("Saint Lucia", "Saint Lucia"),
    "VC": ("Saint Vincent and the Grenadines", "Saint Vincent dan Grenadine"),
    "WS": ("Samoa", "Samoa"),
    "SM": ("San Marino", "San Marino"),
    "ST": ("Sao Tome and Principe", "Sao Tome dan Principe"),
    "SA": ("Saudi Arabia", "Arab Saudi"),
    "SN": ("Senegal", "Senegal"),
    "RS": ("Serbia", "Serbia"),
    "SC": ("Seychelles", "Seychelles"),
    "SL": ("Sierra Leone", "Sierra Leone"),
    "SG": ("Singapore", "Singapura"),
    "SK": ("Slovakia", "Slowakia"),
    "SI": ("Slovenia", "Slovenia"),
    "SB": ("Solomon Islands", "Kepulauan Solomon"),
    "SO": ("Somalia", "Somalia"),
    "ZA": ("South Africa", "Afrika Selatan"),
    "KR": ("South Korea", "Korea Selatan"),
    "SS": ("South Sudan", "Sudan Selatan"),
    "ES": ("Spain", "Spanyol"),
    "LK": ("Sri Lanka", "Sri Lanka"),
    "SD": ("Sudan", "Sudan"),
    "SR": ("Suriname", "Suriname"),
    "SE": ("Sweden", "Swedia"),
    "CH_LI": ("Switzerland or Liechtenstein", "Swiss atau Liechtenstein"),
    "SY": ("Syria", "Suriah"),
    "TW": ("Taiwan", "Taiwan"),
    "TJ": ("Tajikistan", "Tajikistan"),
    "TZ": ("Tanzania", "Tanzania"),
    "TH": ("Thailand", "Thailand"),
    "TG": ("Togo", "Togo"),
    "TO": ("Tonga", "Tonga"),
    "TT": ("Trinidad and Tobago", "Trinidad dan Tobago"),
    "TN": ("Tunisia", "Tunisia"),
    "TR": ("Türkiye", "Turki"),
    "TM": ("Turkmenistan", "Turkmenistan"),
    "TC": ("Turks and Caicos Islands", "Kepulauan Turks dan Caicos"),
    "TV": ("Tuvalu", "Tuvalu"),
    "UG": ("Uganda", "Uganda"),
    "UA": ("Ukraine", "Ukraina"),
    "AE": ("United Arab Emirates", "Uni Emirat Arab"),
    "GB": ("United Kingdom", "Inggris"),
    "US": ("United States", "Amerika Serikat"),
    "UY": ("Uruguay", "Uruguay"),
    "UZ": ("Uzbekistan", "Uzbekistan"),
    "VU": ("Vanuatu", "Vanuatu"),
    "VE": ("Venezuela", "Venezuela"),
    "VN": ("Vietnam", "Vietnam"),
    "YE": ("Yemen", "Yaman"),
    "ZM": ("Zambia", "Zambia"),
    "ZW": ("Zimbabwe", "Zimbabwe"),
}

# Prefix (the part before the dash) -> country. "B", "F", "VP" and "VQ" need
# the letters after the dash too and are resolved in country_key().
PREFIXES = {
    "YA": "AF", "ZA": "AL", "7T": "DZ", "C3": "AD", "D2": "AO", "V2": "AG",
    "LV": "AR", "LQ": "AR", "EK": "AM", "P4": "AW", "VH": "AU", "OE": "AT",
    "4K": "AZ", "C6": "BS", "A9C": "BH", "S2": "BD", "8P": "BB", "EW": "BY",
    "OO": "BE", "V3": "BZ", "TY": "BJ", "A5": "BT", "CP": "BO", "E7": "BA",
    "A2": "BW", "PP": "BR", "PR": "BR", "PS": "BR", "PT": "BR", "PU": "BR",
    "V8": "BN", "LZ": "BG", "XT": "BF", "9U": "BI", "XU": "KH", "TJ": "CM",
    "C": "CA", "D4": "CV", "TL": "CF", "TT": "TD", "CC": "CL", "HJ": "CO",
    "HK": "CO", "D6": "KM", "TN": "CG", "9S": "CD", "9T": "CD", "E5": "CK",
    "TI": "CR", "9A": "HR", "CU": "CU", "5B": "CY", "OK": "CZ", "OY": "DK",
    "J2": "DJ", "J7": "DM", "HI": "DO", "4W": "TL", "HC": "EC", "SU": "EG",
    "YS": "SV", "3C": "GQ", "E3": "ER", "ES": "EE", "3D": "SZ", "3DC": "SZ",
    "ET": "ET", "DQ": "FJ", "OH": "FI", "TR": "GA", "C5": "GM", "4L": "GE",
    "D": "DE", "9G": "GH", "SX": "GR", "J3": "GD", "TG": "GT", "2": "GG",
    "3X": "GN", "J5": "GW", "8R": "GY", "HH": "HT", "HR": "HN", "HA": "HU",
    "TF": "IS", "VT": "IN", "PK": "ID", "EP": "IR", "YI": "IQ", "EI": "IE",
    "EJ": "IE", "M": "IM", "4X": "IL", "4Z": "IL", "I": "IT", "TU": "CI",
    "6Y": "JM", "JA": "JP", "JR": "JP", "JY": "JO", "UP": "KZ", "5Y": "KE",
    "T3": "KI", "Z6": "XK", "9K": "KW", "EX": "KG", "RDPL": "LA", "YL": "LV",
    "OD": "LB", "7P": "LS", "A8": "LR", "5A": "LY", "LY": "LT", "LX": "LU",
    "5R": "MG", "7Q": "MW", "9M": "MY", "8Q": "MV", "TZ": "ML", "9H": "MT",
    "V7": "MH", "5T": "MR", "3B": "MU", "XA": "MX", "XB": "MX", "XC": "MX",
    "V6": "FM", "ER": "MD", "3A": "MC", "JU": "MN", "4O": "ME", "CN": "MA",
    "C9": "MZ", "XY": "MM", "XZ": "MM", "V5": "NA", "C2": "NR", "9N": "NP",
    "PH": "NL", "PJ": "NL_CARIBBEAN", "ZK": "NZ", "ZL": "NZ", "ZM": "NZ",
    "YN": "NI", "5U": "NE", "5N": "NG", "P": "KP", "Z3": "MK", "LN": "NO",
    "A4O": "OM", "AP": "PK", "HP": "PA", "P2": "PG", "ZP": "PY", "OB": "PE",
    "RP": "PH", "SP": "PL", "SN": "PL", "CR": "PT", "CS": "PT", "A7": "QA",
    "YR": "RO", "RA": "RU", "RF": "RU", "9XR": "RW", "V4": "KN", "J6": "LC",
    "J8": "VC", "5W": "WS", "T7": "SM", "S9": "ST", "HZ": "SA", "6V": "SN",
    "6W": "SN", "YU": "RS", "S7": "SC", "9L": "SL", "9V": "SG", "OM": "SK",
    "S5": "SI", "H4": "SB", "6O": "SO", "ZS": "ZA", "ZT": "ZA", "ZU": "ZA",
    "HL": "KR", "Z8": "SS", "EC": "ES", "EM": "ES", "4R": "LK", "ST": "SD",
    "PZ": "SR", "SE": "SE", "HB": "CH_LI", "YK": "SY", "EY": "TJ", "5H": "TZ",
    "HS": "TH", "5V": "TG", "A3": "TO", "9Y": "TT", "TS": "TN", "TC": "TR",
    "EZ": "TM", "T2": "TV", "5X": "UG", "UR": "UA", "A6": "AE", "DU": "AE",
    "G": "GB", "N": "US", "F": "FR", "CX": "UY", "UK": "UZ", "YJ": "VU", "YV": "VE",
    "VN": "VN", "7O": "YE", "9J": "ZM", "Z": "ZW",
}

# British Overseas Territories share VP- and VQ-; the next letter decides.
_VP_VQ = {
    "VP-A": "AI", "VP-B": "BM", "VQ-B": "BM", "VP-C": "KY", "VQ-C": "KY",
    "VP-F": "FK", "VP-G": "GI", "VP-L": "VG", "VP-M": "MS", "VQ-H": "SH",
    "VQ-T": "TC",
}

# Written without a dash (a callsign that is the registration), these are
# recognisable by shape.
_NO_DASH = (
    ("US", re.compile(r"^N[1-9][0-9A-Z]{0,4}$")),
    ("JP", re.compile(r"^JA[0-9][0-9A-Z]{3}$")),
    ("KR", re.compile(r"^HL[0-9]{4}$")),
)
_LONGEST_FIRST = sorted(PREFIXES, key=len, reverse=True)


def _chinese_area(mark):
    """B- is shared: B-H/K/L Hong Kong, B-M Macau, five digits Taiwan,
    anything else (B-1234, B-30AE) mainland China."""
    if not mark:
        return None
    if mark[0] in "HKL":
        return "HK"
    if mark[0] == "M":
        return "MO"
    if re.fullmatch(r"[0-9]{5}", mark):
        return "TW"
    return "CN"


def country_key(registration):
    """The COUNTRIES key for a registration ("9V-TNG", "B-HLA", "N71108",
    "9VTNG"), or None when it can't be placed with confidence."""
    reg = (registration or "").strip().upper().replace(" ", "")
    if not reg:
        return None
    if "-" in reg:
        head, mark = reg.split("-", 1)
        if head == "B":
            return _chinese_area(mark)
        if head in ("VP", "VQ"):
            return _VP_VQ.get(f"{head}-{mark[:1]}")
        if head == "F":
            return "FR_OVERSEAS" if mark.startswith("O") else "FR"
        return PREFIXES.get(head)
    for key, pattern in _NO_DASH:
        if pattern.match(reg):
            return key
    # A known prefix followed by 3 or 4 letters, e.g. "9VTNG", "PKGPA", "DAIMA".
    for head in _LONGEST_FIRST:
        mark = reg[len(head):]
        if reg.startswith(head) and 3 <= len(mark) <= 4 and mark.isalpha():
            return PREFIXES[head]
    return None


def country_name(registration, language="en"):
    """The country or territory of a registration in "en" or "id", or None."""
    key = country_key(registration)
    if key is None:
        return None
    english, indonesian = COUNTRIES[key]
    return indonesian if (language or "").lower().startswith("id") else english
