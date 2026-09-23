# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Airports for Flight Radar's "Listen to ATC": every large and medium airport in
Indonesia plus the big airports near Indonesia and the main regional hubs
(Singapore, Kuala Lumpur, Bangkok, Manila, Perth, Darwin...). Used to find the
airport nearest to an aircraft or to the chosen city. Pure data and geometry.
"""

import re

import flight_radar_api as api

# Airport data from OurAirports (https://ourairports.com/data/), public domain.
# (ICAO code, city, airport name, latitude, longitude)
AIRPORTS = (
    ('WAAA', 'Makassar', 'Sultan Hasanuddin', -5.0755, 119.5537),
    ('WABB', 'Biak', 'Frans Kaisiepo', -1.19, 136.108),
    ('WABI', 'Nabire', 'Douw Aturure', -3.398, 135.3931),
    ('WABO', 'Serui', 'Stevanus Rumbewas', -1.8284, 136.0624),
    ('WADB', 'Bima', 'Sultan Muhammad Salahuddin', -8.5372, 118.685),
    ('WADD', 'Denpasar', 'Denpasar I Gusti Ngurah Rai', -8.7484, 115.1671),
    ('WADL', 'Lombok', 'Lombok', -8.76, 116.2782),
    ('WAEE', 'Ternate', 'Sultan Babullah', 0.831, 127.3816),
    ('WAEW', 'Gotalalamo', 'Pitu', 2.046, 128.325),
    ('WAFB', 'Toraja', 'Toraja', -3.1844, 119.9191),
    ('WAFF', 'Palu', 'Mutiara - SIS Al-Jufrie', -0.9165, 119.9086),
    ('WAFP', 'Poso', 'Kasiguncu', -1.4141, 120.6592),
    ('WAFW', 'Luwok', 'Syukuran Aminuddin Amir', -1.0359, 122.7739),
    ('WAGG', 'Palangkaraya', 'Tjilik Riwut', -2.2271, 113.9434),
    ('WAHH', 'Yogyakarta', 'Adisutjipto', -7.7882, 110.432),
    ('WAHI', 'Yogyakarta', 'Yogyakarta', -7.9053, 110.0573),
    ('WAHL', 'Cilacap', 'Tunggul Wulung', -7.6451, 109.034),
    ('WAHQ', 'Surakarta', 'Adisoemarmo', -7.516, 110.7575),
    ('WAHS', 'Semarang', 'Jenderal Ahmad Yani', -6.9707, 110.3732),
    ('WAJJ', 'Jayapura', 'Dortheys Hiyo Eluay', -2.5796, 140.5199),
    ('WAJO', 'Oksibil', 'Oksibil', -4.9071, 140.6277),
    ('WAKK', 'Merauke', 'Mopah', -8.5239, 140.4197),
    ('WAKT', 'Tanah Merah', 'Tanah Merah', -6.0967, 140.3035),
    ('WALK', 'Nusantara', 'Nusantara', -1.1605, 116.7119),
    ('WALL', 'Balikpapan', 'Sultan Aji Muhammad Sulaiman Sepinggan', -1.2683, 116.8945),
    ('WALS', 'Samarinda', 'Aji Pangeran Tumenggung Pranoto', -0.3745, 117.2501),
    ('WAMH', 'Tabukan Utara', 'Naha', 3.6848, 125.5272),
    ('WAMM', 'Manado', 'Sam Ratulangi', 1.5486, 124.9262),
    ('WAON', 'Tanta-Tabalong', 'Warukin', -2.2166, 115.436),
    ('WAOO', 'Banjarmasin', 'Syamsudin Noor', -3.4401, 114.7612),
    ('WAPF', 'Langgur', 'Karel Sadsuitubun', -5.7603, 132.7594),
    ('WAPN', 'Namniwel', 'Namniwel', -3.1432, 126.9765),
    ('WAPP', 'Ambon', 'Pattimura', -3.7103, 128.089),
    ('WAQQ', 'Tarakan', 'Juwata', 3.3251, 117.5642),
    ('WAQT', 'Tanjung Redeb', 'Kalimarau', 2.1478, 117.4307),
    ('WARA', 'Malang', 'Abdul Rachman Saleh', -7.9291, 112.7142),
    ('WARD', 'Kediri', 'Dhoho', -7.7495, 111.9468),
    ('WARR', 'Surabaya', 'Juanda', -7.3798, 112.787),
    ('WASF', 'Fakfak', 'Fakfak', -2.9205, 132.267),
    ('WASK', 'Kaimana', 'Utarom', -3.6446, 133.6951),
    ('WASO', 'Babo', 'Babo', -2.5322, 133.439),
    ('WASS', 'Sorong', 'Domine Eduard Osok', -0.894, 131.287),
    ('WATT', 'Kupang', 'El Tari', -10.1716, 123.671),
    ('WAUU', 'Manokwari', 'Rendani', -0.8918, 134.049),
    ('WAVV', 'Wamena', 'Wamena', -4.0973, 138.9524),
    ('WAWD', 'Wangi-wangi Island', 'Matahora', -5.2921, 123.6362),
    ('WAWP', 'Kolaka', 'Sangia Nibandera', -4.3382, 121.524),
    ('WAYB', 'Bilogai', 'Bilorai', -3.7395, 137.0312),
    ('WAYY', 'Timika', 'Mozes Kilangin', -4.5298, 136.8874),
    ('WIBB', 'Pekanbaru', 'Sultan Syarif Kasim II', 0.4586, 101.4443),
    ('WIBD', 'Dumai', 'Pinang Kampai', 1.609, 101.4335),
    ('WIBJ', 'Rengat', 'Japura', -0.3528, 102.335),
    ('WICA', 'Kertajati', 'Kertajati', -6.6474, 108.1656),
    ('WICC', 'Bandung', 'Husein Sastranegara', -6.9006, 107.576),
    ('WIDD', 'Batam', 'Hang Nadim', 1.121, 104.119),
    ('WIDN', 'Tanjung Pinang', 'Raja Haji Fisabilillah', 0.924, 104.5334),
    ('WIDO', 'Ranai', 'Ranai', 3.9087, 108.388),
    ('WIEE', 'Padang', 'Minangkabau', -0.786, 100.2804),
    ('WIGG', 'Bengkulu', 'Fatmawati Soekarno', -3.8637, 102.339),
    ('WIHH', 'Jakarta', 'Halim Perdanakusuma', -6.267, 106.8903),
    ('WIII', 'Jakarta', 'Soekarno-Hatta', -6.1256, 106.656),
    ('WIKK', 'Pangkal Pinang', 'Depati Amir', -2.1622, 106.139),
    ('WILL', 'Bandar Lampung', 'Radin Inten II', -5.2468, 105.1825),
    ('WIMB', 'Gunungsitoli', 'Binaka', 1.1663, 97.7052),
    ('WIME', 'Padang Sidempuan', 'Aek Godang', 1.4001, 99.4305),
    ('WIMK', 'Medan', 'Soewondo Air Force Base', 3.5584, 98.6723),
    ('WIMM', 'Medan', 'Kualanamu', 3.6378, 98.8706),
    ('WIMS', 'Sibolga', 'Dr. Ferdinand Lumban Tobing', 1.5571, 98.8871),
    ('WIMU', 'Kutacane', 'Alas Leuser', 3.3915, 97.8637),
    ('WIOG', 'Nanga Pinoh', 'Nanga Pinoh', -0.3486, 111.7462),
    ('WIOK', 'Ketapang', 'Rahadi Osman', -1.8172, 109.9635),
    ('WIOO', 'Pontianak', 'Supadio', -0.1523, 109.4045),
    ('WIOP', 'Putussibau', 'Pangsuma', 0.8346, 112.9402),
    ('WIOS', 'Sintang', 'Tebelian', -0.0452, 111.458),
    ('WIPP', 'Palembang', 'Sultan Mahmud Badaruddin II', -2.8977, 104.6981),
    ('WIPQ', 'Talang Gudang', 'Pendopo', -3.2861, 103.88),
    ('WITC', 'Kuala Pesisir', 'Cut Nyak Dhien', 4.041, 96.2533),
    ('WITK', 'Takengon', 'Rembele', 4.7211, 96.8519),
    ('WITL', 'Lhok Sukon', 'Lhok Sukon', 5.0695, 97.2592),
    ('WITT', 'Banda Aceh', 'Sultan Iskandar Muda', 5.5251, 95.42),
    ('AYNZ', 'Lae', 'Nadzab Tomodachi', -6.568, 146.7265),
    ('AYPY', 'Port Moresby', 'Port Moresby Jacksons', -9.4434, 147.22),
    ('RPLL', 'Manila', 'Ninoy Aquino', 14.5086, 121.02),
    ('RPMD', 'Davao', 'Francisco Bangoy', 7.1255, 125.646),
    ('RPMR', 'General Santos', 'General Santos', 6.0572, 125.0962),
    ('RPMY', 'Laguindingan', 'Laguindingan', 8.6122, 124.4565),
    ('RPMZ', 'Zamboanga', 'Zamboanga', 6.9224, 122.06),
    ('RPSP', 'Panglao', 'Bohol-Panglao', 9.573, 123.7701),
    ('RPVM', 'Cebu', 'Mactan Cebu', 10.3093, 123.9797),
    ('RPVP', 'Puerto Princesa', 'Puerto Princesa', 9.742, 118.7591),
    ('VOPB', 'Port Blair', 'Veer Savarkar', 11.6402, 92.729),
    ('VTBD', 'Bangkok', 'Don Mueang', 13.9126, 100.607),
    ('VTBS', 'Bangkok', 'Suvarnabhumi', 13.6811, 100.747),
    ('VTSG', 'Krabi', 'Krabi', 8.0956, 98.989),
    ('VTSM', '', 'Ko Samui', 9.5478, 100.062),
    ('VTSP', 'Phuket', 'Phuket', 8.1133, 98.3174),
    ('VTSS', 'Hat Yai', 'Hat Yai', 6.9332, 100.393),
    ('VVCT', 'Can Tho', 'Can Tho', 10.0834, 105.7094),
    ('VVTS', 'Ho Chi Minh City', 'Tan Son Nhat', 10.8188, 106.652),
    ('WBGG', 'Kuching', 'Kuching', 1.4874, 110.3529),
    ('WBKK', 'Kota Kinabalu', 'Kota Kinabalu', 5.9327, 116.0493),
    ('WBSB', 'Brunei', 'Brunei', 4.9442, 114.928),
    ('WMKI', 'Ipoh', 'Sultan Azlan Shah', 4.5673, 101.0916),
    ('WMKJ', 'Johor Bahru', 'Senai', 1.6413, 103.67),
    ('WMKK', 'Kuala Lumpur', 'Kuala Lumpur', 2.7456, 101.71),
    ('WMKL', 'Langkawi', 'Langkawi', 6.3297, 99.7287),
    ('WMKP', 'Penang', 'Penang', 5.2963, 100.2762),
    ('WMSA', 'Kuala Lumpur', 'Sultan Abdul Aziz Shah', 3.1306, 101.549),
    ('WPDL', 'Dili', 'Presidente Nicolau Lobato', -8.5466, 125.5245),
    ('WPOC', '', 'Oecusse', -9.1984, 124.3379),
    ('WSSS', 'Singapore', 'Singapore Changi', 1.3502, 103.994),
    ('YPDN', 'Darwin', 'Darwin', -12.415, 130.8818),
    ('YPPH', 'Perth', 'Perth', -31.9403, 115.967),
)

_BY_ICAO = {row[0]: row for row in AIRPORTS}
_SUFFIX = re.compile(r"\s+(International\s+)?Airport$", re.IGNORECASE)


def _entry(row):
    icao, city, name, lat, lon = row
    return {"icao": icao, "city": city, "name": name, "latitude": lat, "longitude": lon}


def by_icao(icao):
    """The airport with this ICAO code, or None."""
    row = _BY_ICAO.get((icao or "").strip().upper())
    return _entry(row) if row else None


def short_name(name):
    """"Soekarno-Hatta International Airport" -> "Soekarno-Hatta"."""
    return _SUFFIX.sub("", (name or "").split(" / ")[0]).strip()


def label(airport):
    """What to call an airport aloud: "Jakarta Soekarno-Hatta", "Singapore Changi"."""
    city, name = (airport.get("city") or "").strip(), (airport.get("name") or "").strip()
    if not city or city.lower() in name.lower():
        return name or city
    if not name:
        return city
    return f"{city} {name}"


def nearest(latitude, longitude, max_km=None, among=None):
    """The airport nearest to a point, with its "distance_km", or None (also
    when the nearest is farther than `max_km`). `among` limits the ICAO codes."""
    best, best_km = None, None
    for row in AIRPORTS:
        if among is not None and row[0] not in among:
            continue
        km = api.distance_and_bearing(latitude, longitude, row[3], row[4])[0]
        if best_km is None or km < best_km:
            best, best_km = row, km
    if best is None or (max_km is not None and best_km > max_km):
        return None
    airport = _entry(best)
    airport["distance_km"] = best_km
    return airport
