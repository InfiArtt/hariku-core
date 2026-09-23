# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Spoken names for airline callsign prefixes (ICAO airline designators) and ICAO
aircraft type designators. Proper names, so the same in every language.
Written for Hariku; kept short so a screen reader says them quickly.
"""

AIRLINES = {
    # Indonesia
    "GIA": "Garuda Indonesia",
    "CTV": "Citilink",
    "LNI": "Lion Air",
    "BTK": "Batik Air",
    "AWQ": "Indonesia AirAsia",
    "SJY": "Sriwijaya Air",
    "WON": "Wings Air",
    "TGN": "Trigana Air",
    "SJV": "Super Air Jet",
    "PAS": "Pelita Air",
    "TNU": "TransNusa",
    "SQS": "Susi Air",
    "AFE": "Airfast Indonesia",
    # Southeast Asia
    "SIA": "Singapore Airlines",
    "SQC": "Singapore Airlines Cargo",
    "TGW": "Scoot",
    "MAS": "Malaysia Airlines",
    "AXM": "AirAsia",
    "XAX": "AirAsia X",
    "MXD": "Batik Air Malaysia",
    "THA": "Thai Airways",
    "AIQ": "Thai AirAsia",
    "TLM": "Thai Lion Air",
    "BKP": "Bangkok Airways",
    "NOK": "Nok Air",
    "TVJ": "Thai Vietjet",
    "PAL": "Philippine Airlines",
    "CEB": "Cebu Pacific",
    "HVN": "Vietnam Airlines",
    "VJC": "VietJet Air",
    "RBA": "Royal Brunei Airlines",
    "LAO": "Lao Airlines",
    # East Asia
    "CPA": "Cathay Pacific",
    "HKE": "HK Express",
    "CES": "China Eastern",
    "CSN": "China Southern",
    "CCA": "Air China",
    "CXA": "Xiamen Airlines",
    "CSZ": "Shenzhen Airlines",
    "CSC": "Sichuan Airlines",
    "CHH": "Hainan Airlines",
    "CSH": "Shanghai Airlines",
    "JAL": "Japan Airlines",
    "ANA": "All Nippon Airways",
    "KAL": "Korean Air",
    "AAR": "Asiana Airlines",
    "JJA": "Jeju Air",
    "JNA": "Jin Air",
    "TWB": "T'way Air",
    "EVA": "EVA Air",
    "CAL": "China Airlines",
    # South Asia
    "AIC": "Air India",
    "AXB": "Air India Express",
    "IGO": "IndiGo",
    "ALK": "SriLankan Airlines",
    "PIA": "Pakistan International Airlines",
    # Oceania
    "QFA": "Qantas",
    "JST": "Jetstar",
    "VOZ": "Virgin Australia",
    "ANZ": "Air New Zealand",
    "ANG": "Air Niugini",
    "FJI": "Fiji Airways",
    # Middle East and Africa
    "UAE": "Emirates",
    "QTR": "Qatar Airways",
    "ETD": "Etihad Airways",
    "SVA": "Saudia",
    "FDB": "flydubai",
    "OMA": "Oman Air",
    "GFA": "Gulf Air",
    "KAC": "Kuwait Airways",
    "MSR": "EgyptAir",
    "ETH": "Ethiopian Airlines",
    # Europe and the Americas
    "THY": "Turkish Airlines",
    "KLM": "KLM",
    "AFR": "Air France",
    "DLH": "Lufthansa",
    "BAW": "British Airways",
    "FIN": "Finnair",
    "UAL": "United Airlines",
    "DAL": "Delta Air Lines",
    "AAL": "American Airlines",
    # Cargo
    "FDX": "FedEx",
    "UPS": "UPS Airlines",
    "CLX": "Cargolux",
    "GTI": "Atlas Air",
    "CKS": "Kalitta Air",
}

AIRCRAFT_TYPES = {
    # Airbus
    "A306": "Airbus A300-600",
    "A310": "Airbus A310",
    "A318": "Airbus A318",
    "A319": "Airbus A319",
    "A320": "Airbus A320",
    "A321": "Airbus A321",
    "A19N": "Airbus A319neo",
    "A20N": "Airbus A320neo",
    "A21N": "Airbus A321neo",
    "A332": "Airbus A330-200",
    "A333": "Airbus A330-300",
    "A338": "Airbus A330-800",
    "A339": "Airbus A330-900",
    "A343": "Airbus A340-300",
    "A346": "Airbus A340-600",
    "A359": "Airbus A350-900",
    "A35K": "Airbus A350-1000",
    "A388": "Airbus A380",
    "BCS1": "Airbus A220-100",
    "BCS3": "Airbus A220-300",
    "A400": "Airbus A400M",
    "C295": "Airbus C295",
    # Boeing
    "B712": "Boeing 717",
    "B733": "Boeing 737-300",
    "B734": "Boeing 737-400",
    "B735": "Boeing 737-500",
    "B736": "Boeing 737-600",
    "B737": "Boeing 737-700",
    "B738": "Boeing 737-800",
    "B739": "Boeing 737-900",
    "B37M": "Boeing 737 MAX 7",
    "B38M": "Boeing 737 MAX 8",
    "B39M": "Boeing 737 MAX 9",
    "B3XM": "Boeing 737 MAX 10",
    "B744": "Boeing 747-400",
    "B748": "Boeing 747-8",
    "B752": "Boeing 757-200",
    "B763": "Boeing 767-300",
    "B764": "Boeing 767-400",
    "B772": "Boeing 777-200",
    "B77L": "Boeing 777-200LR",
    "B773": "Boeing 777-300",
    "B77W": "Boeing 777-300ER",
    "B778": "Boeing 777-8",
    "B779": "Boeing 777-9",
    "B788": "Boeing 787-8",
    "B789": "Boeing 787-9",
    "B78X": "Boeing 787-10",
    "MD11": "McDonnell Douglas MD-11",
    # Regional airliners
    "AT43": "ATR 42-300",
    "AT45": "ATR 42-500",
    "AT46": "ATR 42-600",
    "AT72": "ATR 72",
    "AT75": "ATR 72-500",
    "AT76": "ATR 72-600",
    "DH8A": "Dash 8-100",
    "DH8B": "Dash 8-200",
    "DH8C": "Dash 8-300",
    "DH8D": "Dash 8-400",
    "E145": "Embraer ERJ 145",
    "E170": "Embraer 170",
    "E75L": "Embraer 175",
    "E75S": "Embraer 175",
    "E190": "Embraer 190",
    "E195": "Embraer 195",
    "E290": "Embraer E190-E2",
    "E295": "Embraer E195-E2",
    "CRJ2": "Bombardier CRJ200",
    "CRJ7": "Bombardier CRJ700",
    "CRJ9": "Bombardier CRJ900",
    "CRJX": "Bombardier CRJ1000",
    "F100": "Fokker 100",
    "F70": "Fokker 70",
    "F50": "Fokker 50",
    "SF34": "Saab 340",
    "CN35": "CN-235",
    "C130": "Lockheed C-130 Hercules",
    "C30J": "Lockheed C-130J Super Hercules",
    # Small aircraft
    "DHC6": "Twin Otter",
    "C208": "Cessna Caravan",
    "C152": "Cessna 152",
    "C172": "Cessna 172",
    "C182": "Cessna 182",
    "PC12": "Pilatus PC-12",
    "PC6T": "Pilatus Porter",
    "BE20": "Beechcraft King Air 200",
    "B350": "Beechcraft King Air 350",
    "BE9L": "Beechcraft King Air 90",
    "DA40": "Diamond DA40",
    "DA42": "Diamond DA42",
    "P28A": "Piper Cherokee",
    # Business jets
    "GLF4": "Gulfstream IV",
    "GLF5": "Gulfstream V",
    "GLF6": "Gulfstream G650",
    "GLEX": "Bombardier Global Express",
    "GL5T": "Bombardier Global 5000",
    "GL7T": "Bombardier Global 7500",
    "CL60": "Bombardier Challenger 600",
    "C56X": "Cessna Citation Excel",
    "C68A": "Cessna Citation Latitude",
    "E55P": "Embraer Phenom 300",
    "FA7X": "Dassault Falcon 7X",
    "F900": "Dassault Falcon 900",
    "LJ45": "Learjet 45",
    "H25B": "Hawker 800",
    # Helicopters
    "EC35": "Airbus H135",
    "EC45": "Airbus H145",
    "AS50": "Airbus AS350",
    "AS65": "Airbus Dauphin",
    "EC30": "Airbus H130",
    "B412": "Bell 412",
    "B429": "Bell 429",
    "AW39": "Leonardo AW139",
    "S76": "Sikorsky S-76",
    "R44": "Robinson R44",
    "R22": "Robinson R22",
}


# Rotorcraft among the types above; the text module adds a translated word.
HELICOPTER_TYPES = frozenset(("EC35", "EC45", "AS50", "AS65", "EC30", "B412", "B429",
                              "AW39", "S76", "R44", "R22"))


def airline_name(prefix):
    """The airline for a 3-letter ICAO callsign prefix, or None."""
    return AIRLINES.get((prefix or "").strip().upper())


def aircraft_type_name(code):
    """The model name for an ICAO type designator, or None."""
    return AIRCRAFT_TYPES.get((code or "").strip().upper())


def is_helicopter(type_code, category=""):
    """True for ADS-B emitter category A7 (rotorcraft) or a known helicopter type."""
    return (category or "").upper() == "A7" or (type_code or "").upper() in HELICOPTER_TYPES
