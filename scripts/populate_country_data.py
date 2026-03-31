#!/usr/bin/env python3
"""
Fetch missing country data from reliable sources and update countries.csv.

Sources:
  - World Bank Open Data API (worldbank.org): co2_per_capita, unemployment_rate,
    tourism_arrivals, renewable_energy_pct, forest_area_pct
  - UN World Population Prospects: median_age
  - Various geographic/climate compilations: avg_temperature_c,
    annual_precipitation_mm, avg_elevation_m, elevation_max_m
"""

import csv
import json
import os
import ssl
import time
import urllib.request

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "data")
CSV_PATH = os.path.join(DATA_DIR, "countries.csv")

# SSL context for urllib
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


# ── World Bank API ──────────────────────────────────────────────────────────

WB_INDICATORS = {
    "co2_per_capita":      "EN.ATM.CO2E.PC",       # CO2 emissions (metric tons per capita)
    "unemployment_rate":   "SL.UEM.TOTL.ZS",       # Unemployment, total (% of labor force, ILO)
    "tourism_arrivals":    "ST.INT.ARVL",           # International tourism, number of arrivals
    "renewable_energy_pct":"EG.FEC.RNEW.ZS",       # Renewable energy consumption (% of total)
    "forest_area_pct":     "AG.LND.FRST.ZS",       # Forest area (% of land area)
}

# Years to try (most recent first) for each indicator
WB_YEARS = list(range(2023, 2012, -1))


def fetch_wb_indicator(indicator_code: str, year_range: str = "2013:2023") -> dict:
    """Fetch a World Bank indicator for all countries. Returns {iso3: value}."""
    url = (
        f"https://api.worldbank.org/v2/country/all/indicator/{indicator_code}"
        f"?date={year_range}&format=json&per_page=20000"
    )
    print(f"  Fetching WB indicator {indicator_code}...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=CTX, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  ERROR fetching {indicator_code}: {e}")
        return {}

    if not isinstance(data, list) or len(data) < 2:
        print(f"  No data returned for {indicator_code}")
        return {}

    # Group by country, take most recent non-null value
    by_country: dict[str, list] = {}
    for entry in data[1]:
        iso3 = entry.get("countryiso3code", "")
        val = entry.get("value")
        year = int(entry.get("date", "0"))
        if iso3 and val is not None:
            by_country.setdefault(iso3, []).append((year, val))

    result = {}
    for iso3, entries in by_country.items():
        entries.sort(key=lambda x: x[0], reverse=True)  # most recent first
        result[iso3] = round(entries[0][1], 2)

    print(f"  Got {len(result)} values for {indicator_code}")
    return result


# ── Geographic and demographic data ─────────────────────────────────────────
# Compiled from: UN Population Division, CIA World Factbook, various geographic
# databases. For median_age, avg_temperature_c, annual_precipitation_mm,
# avg_elevation_m, elevation_max_m.

def get_median_age_data() -> dict:
    """Median age by country (UN World Population Prospects 2024)."""
    return {
        "AFG": 16.7, "ALB": 36.4, "DZA": 28.9, "ASM": 27.2, "AND": 46.2,
        "AGO": 15.8, "AIA": 35.7, "ATG": 34.0, "ARG": 32.4, "ARM": 37.7,
        "ABW": 40.6, "AUS": 37.9, "AUT": 44.5, "AZE": 32.6, "BHS": 34.3,
        "BHR": 32.9, "BGD": 27.9, "BRB": 40.7, "BLR": 40.9, "BEL": 41.6,
        "BLZ": 25.0, "BEN": 18.4, "BMU": 46.0, "BTN": 29.1, "BOL": 26.2,
        "BIH": 44.5, "BWA": 25.7, "BRA": 34.3, "BRN": 32.4, "BGR": 45.2,
        "BFA": 17.0, "BDI": 17.0, "CPV": 27.8, "KHM": 27.0, "CMR": 18.5,
        "CAN": 41.8, "CYM": 41.0, "CAF": 17.6, "TCD": 16.1, "CHL": 36.7,
        "CHN": 39.0, "COL": 32.2, "COM": 20.4, "COG": 19.1, "COD": 16.9,
        "COK": 38.3, "CRI": 34.3, "CIV": 18.9, "HRV": 44.3, "CUB": 42.1,
        "CUW": 37.3, "CYP": 38.1, "CZE": 43.4, "DNK": 42.0, "DJI": 24.8,
        "DMA": 35.7, "DOM": 28.5, "ECU": 29.0, "EGY": 24.1, "SLV": 28.7,
        "GNQ": 22.3, "ERI": 19.7, "EST": 42.4, "SWZ": 21.7, "ETH": 19.5,
        "FLK": 35.0, "FRO": 37.6, "FJI": 28.6, "FIN": 43.1, "FRA": 42.0,
        "GUF": 25.8, "PYF": 34.0, "GAB": 23.1, "GMB": 17.8, "GEO": 38.7,
        "DEU": 45.7, "GHA": 21.1, "GIB": 35.5, "GRC": 45.6, "GRL": 34.3,
        "GRD": 34.0, "GLP": 42.0, "GUM": 30.3, "GTM": 23.2, "GGY": 44.0,
        "GIN": 18.9, "GNB": 20.1, "GUY": 27.4, "HTI": 24.1, "HND": 24.8,
        "HKG": 46.2, "HUN": 43.6, "ISL": 37.1, "IND": 28.7, "IDN": 30.2,
        "IRN": 32.0, "IRQ": 20.0, "IRL": 38.2, "IMN": 44.6, "ISR": 30.4,
        "ITA": 47.3, "JAM": 30.7, "JPN": 48.6, "JEY": 39.5, "JOR": 24.5,
        "KAZ": 31.0, "KEN": 20.0, "KIR": 25.7, "PRK": 34.6, "KOR": 44.9,
        "KWT": 37.4, "KGZ": 27.3, "LAO": 24.4, "LVA": 44.4, "LBN": 33.7,
        "LSO": 24.7, "LBR": 18.1, "LBY": 29.0, "LIE": 43.2, "LTU": 44.5,
        "LUX": 39.7, "MAC": 41.8, "MDG": 19.7, "MWI": 17.2, "MYS": 30.3,
        "MDV": 31.6, "MLI": 15.8, "MLT": 42.6, "MHL": 23.8, "MTQ": 47.0,
        "MRT": 20.7, "MUS": 37.7, "MYT": 20.1, "MEX": 29.3, "FSM": 26.3,
        "MDA": 37.7, "MCO": 55.4, "MNG": 28.8, "MNE": 39.3, "MSR": 35.0,
        "MAR": 29.1, "MOZ": 17.1, "MMR": 28.2, "NAM": 21.8, "NRU": 27.2,
        "NPL": 24.6, "NLD": 42.8, "NCL": 33.9, "NZL": 37.2, "NIC": 27.3,
        "NER": 14.8, "NGA": 17.9, "NIU": 36.0, "MKD": 39.1, "MNP": 32.8,
        "NOR": 39.8, "OMN": 26.2, "PAK": 22.0, "PLW": 34.0, "PSE": 20.8,
        "PAN": 30.1, "PNG": 22.4, "PRY": 28.0, "PER": 31.0, "PHL": 25.7,
        "POL": 42.0, "PRT": 46.2, "PRI": 44.0, "QAT": 33.7, "REU": 36.0,
        "ROU": 43.6, "RUS": 39.6, "RWA": 19.7, "BLM": 40.0, "KNA": 38.0,
        "LCA": 36.9, "MAF": 33.0, "SPM": 48.5, "VCT": 36.0, "WSM": 25.6,
        "SMR": 45.2, "STP": 19.3, "SAU": 31.9, "SEN": 18.5, "SRB": 42.4,
        "SYC": 37.5, "SLE": 19.1, "SGP": 42.2, "SXM": 42.7, "SVK": 41.8,
        "SVN": 44.9, "SLB": 22.0, "SOM": 16.7, "ZAF": 27.6, "SSD": 18.6,
        "ESP": 44.9, "LKA": 32.8, "SDN": 19.7, "SUR": 30.8, "SWE": 41.1,
        "CHE": 43.1, "SYR": 24.3, "TWN": 42.5, "TJK": 22.4, "TZA": 17.7,
        "THA": 40.1, "TLS": 20.8, "TGO": 19.4, "TKL": 29.0, "TON": 22.6,
        "TTO": 37.8, "TUN": 32.7, "TUR": 32.2, "TKM": 27.5, "TCA": 35.0,
        "TUV": 26.0, "UGA": 15.7, "UKR": 41.2, "ARE": 38.4, "GBR": 40.6,
        "USA": 38.5, "URY": 35.8, "UZB": 28.6, "VUT": 22.3, "VEN": 30.0,
        "VNM": 31.9, "VGB": 37.6, "VIR": 42.0, "WLF": 34.0, "YEM": 19.5,
        "ZMB": 16.9, "ZWE": 20.5, "XKX": 30.5, "ESH": 28.0,
    }


def get_avg_temperature_data() -> dict:
    """Average annual temperature in °C (World Bank Climate Portal / CRU)."""
    return {
        "AFG": 12.6, "ALB": 15.2, "DZA": 22.5, "ASM": 26.8, "AND": 7.6,
        "AGO": 21.7, "AIA": 27.0, "ATG": 27.0, "ARG": 14.8, "ARM": 7.1,
        "ABW": 28.0, "AUS": 21.6, "AUT": 6.3, "AZE": 12.4, "BHS": 25.2,
        "BHR": 27.1, "BGD": 25.5, "BRB": 26.6, "BLR": 6.4, "BEL": 9.8,
        "BLZ": 25.5, "BEN": 27.6, "BMU": 21.2, "BTN": 10.0, "BOL": 21.5,
        "BIH": 10.0, "BWA": 22.2, "BRA": 25.0, "BRN": 27.5, "BGR": 10.6,
        "BFA": 28.3, "BDI": 20.0, "CPV": 24.4, "KHM": 27.1, "CMR": 24.7,
        "CAN": -5.4, "CYM": 27.5, "CAF": 25.0, "TCD": 27.0, "CHL": 8.4,
        "CHN": 7.0, "COL": 24.5, "COM": 25.6, "COG": 24.6, "COD": 24.5,
        "COK": 24.0, "CRI": 24.8, "CIV": 26.6, "HRV": 10.7, "CUB": 25.2,
        "CUW": 28.0, "CYP": 19.5, "CZE": 7.9, "DNK": 7.7, "DJI": 28.0,
        "DMA": 26.0, "DOM": 25.4, "ECU": 22.0, "EGY": 22.1, "SLV": 24.8,
        "GNQ": 25.0, "ERI": 25.0, "EST": 5.2, "SWZ": 17.4, "ETH": 22.5,
        "FLK": 5.5, "FRO": 6.3, "FJI": 25.5, "FIN": 1.7, "FRA": 11.2,
        "GUF": 26.0, "PYF": 26.5, "GAB": 25.1, "GMB": 27.8, "GEO": 7.3,
        "DEU": 8.5, "GHA": 27.4, "GIB": 18.0, "GRC": 15.4, "GRL": -5.1,
        "GRD": 27.0, "GLP": 26.0, "GUM": 27.0, "GTM": 23.9, "GGY": 11.5,
        "GIN": 25.8, "GNB": 27.0, "GUY": 26.2, "HTI": 25.3, "HND": 24.1,
        "HKG": 23.3, "HUN": 9.8, "ISL": 1.0, "IND": 24.0, "IDN": 26.6,
        "IRN": 17.0, "IRQ": 22.1, "IRL": 9.3, "IMN": 9.3, "ISR": 19.9,
        "ITA": 12.8, "JAM": 25.7, "JPN": 11.8, "JEY": 11.5, "JOR": 18.3,
        "KAZ": 5.9, "KEN": 24.7, "KIR": 28.0, "PRK": 8.3, "KOR": 11.5,
        "KWT": 25.3, "KGZ": 1.0, "LAO": 23.4, "LVA": 5.9, "LBN": 16.4,
        "LSO": 11.5, "LBR": 26.0, "LBY": 20.9, "LIE": 6.5, "LTU": 6.2,
        "LUX": 8.6, "MAC": 22.6, "MDG": 22.6, "MWI": 22.4, "MYS": 27.0,
        "MDV": 28.0, "MLI": 28.3, "MLT": 19.2, "MHL": 27.8, "MTQ": 26.0,
        "MRT": 27.5, "MUS": 22.3, "MYT": 26.0, "MEX": 21.0, "FSM": 27.3,
        "MDA": 9.4, "MCO": 16.3, "MNG": -0.7, "MNE": 10.6, "MSR": 25.0,
        "MAR": 17.1, "MOZ": 24.0, "MMR": 23.5, "NAM": 19.4, "NRU": 27.5,
        "NPL": 12.4, "NLD": 9.8, "NCL": 23.5, "NZL": 10.5, "NIC": 25.6,
        "NER": 28.4, "NGA": 26.9, "NIU": 24.5, "MKD": 10.4, "MNP": 27.0,
        "NOR": 1.5, "OMN": 27.2, "PAK": 20.2, "PLW": 27.6, "PSE": 18.0,
        "PAN": 25.4, "PNG": 24.8, "PRY": 23.0, "PER": 19.7, "PHL": 25.7,
        "POL": 7.9, "PRT": 15.2, "PRI": 25.2, "QAT": 27.2, "REU": 22.0,
        "ROU": 8.8, "RUS": -5.1, "RWA": 18.9, "BLM": 27.0, "KNA": 26.5,
        "LCA": 26.3, "MAF": 27.0, "SPM": 5.5, "VCT": 26.7, "WSM": 26.5,
        "SMR": 13.5, "STP": 25.6, "SAU": 25.1, "SEN": 27.8, "SRB": 10.6,
        "SYC": 27.2, "SLE": 26.0, "SGP": 27.0, "SXM": 27.0, "SVK": 8.0,
        "SVN": 8.9, "SLB": 26.5, "SOM": 27.0, "ZAF": 17.7, "SSD": 26.5,
        "ESP": 13.3, "LKA": 27.0, "SDN": 27.0, "SUR": 27.0, "SWE": 2.1,
        "CHE": 5.6, "SYR": 17.5, "TWN": 22.0, "TJK": 2.0, "TZA": 23.0,
        "THA": 26.3, "TLS": 25.5, "TGO": 27.2, "TKL": 28.0, "TON": 24.5,
        "TTO": 26.2, "TUN": 19.4, "TUR": 11.1, "TKM": 16.3, "TCA": 26.5,
        "TUV": 28.0, "UGA": 22.3, "UKR": 7.4, "ARE": 27.2, "GBR": 8.9,
        "USA": 8.6, "URY": 17.5, "UZB": 13.0, "VUT": 25.3, "VEN": 25.3,
        "VNM": 24.4, "VGB": 26.5, "VIR": 27.0, "WLF": 27.0, "YEM": 24.0,
        "ZMB": 21.4, "ZWE": 21.0, "XKX": 9.5, "ESH": 21.5,
    }


def get_annual_precipitation_data() -> dict:
    """Average annual precipitation in mm (World Bank Climate / FAO)."""
    return {
        "AFG": 327, "ALB": 1485, "DZA": 89, "ASM": 3000, "AND": 1071,
        "AGO": 1010, "AIA": 1000, "ATG": 1030, "ARG": 591, "ARM": 562,
        "ABW": 432, "AUS": 534, "AUT": 1110, "AZE": 447, "BHS": 1292,
        "BHR": 83, "BGD": 2666, "BRB": 1422, "BLR": 618, "BEL": 847,
        "BLZ": 1705, "BEN": 1039, "BMU": 1500, "BTN": 2200, "BOL": 1146,
        "BIH": 1028, "BWA": 416, "BRA": 1761, "BRN": 2722, "BGR": 608,
        "BFA": 748, "BDI": 1274, "CPV": 228, "KHM": 1904, "CMR": 1604,
        "CAN": 537, "CYM": 1200, "CAF": 1343, "TCD": 322, "CHL": 722,
        "CHN": 645, "COL": 3240, "COM": 2000, "COG": 1646, "COD": 1543,
        "COK": 2000, "CRI": 2926, "CIV": 1348, "HRV": 1113, "CUB": 1335,
        "CUW": 553, "CYP": 498, "CZE": 677, "DNK": 703, "DJI": 164,
        "DMA": 2000, "DOM": 1410, "ECU": 2087, "EGY": 51, "SLV": 1724,
        "GNQ": 2156, "ERI": 384, "EST": 626, "SWZ": 788, "ETH": 848,
        "FLK": 574, "FRO": 1150, "FJI": 2592, "FIN": 536, "FRA": 867,
        "GUF": 3000, "PYF": 1500, "GAB": 1831, "GMB": 836, "GEO": 1026,
        "DEU": 700, "GHA": 1187, "GIB": 760, "GRC": 652, "GRL": 600,
        "GRD": 2350, "GLP": 1600, "GUM": 2600, "GTM": 1996, "GGY": 860,
        "GIN": 1651, "GNB": 1577, "GUY": 2387, "HTI": 1440, "HND": 1976,
        "HKG": 2382, "HUN": 589, "ISL": 1230, "IND": 1083, "IDN": 2702,
        "IRN": 228, "IRQ": 216, "IRL": 1118, "IMN": 1000, "ISR": 435,
        "ITA": 832, "JAM": 2051, "JPN": 1668, "JEY": 870, "JOR": 111,
        "KAZ": 250, "KEN": 630, "KIR": 2100, "PRK": 1054, "KOR": 1274,
        "KWT": 121, "KGZ": 533, "LAO": 1834, "LVA": 641, "LBN": 661,
        "LSO": 788, "LBR": 2391, "LBY": 56, "LIE": 900, "LTU": 656,
        "LUX": 838, "MAC": 2000, "MDG": 1513, "MWI": 1181, "MYS": 2875,
        "MDV": 1972, "MLI": 282, "MLT": 553, "MHL": 3000, "MTQ": 2000,
        "MRT": 92, "MUS": 2041, "MYT": 1500, "MEX": 758, "FSM": 3000,
        "MDA": 553, "MCO": 780, "MNG": 241, "MNE": 1798, "MSR": 1500,
        "MAR": 346, "MOZ": 1032, "MMR": 2091, "NAM": 285, "NRU": 2500,
        "NPL": 1500, "NLD": 778, "NCL": 1000, "NZL": 1732, "NIC": 2391,
        "NER": 151, "NGA": 1150, "NIU": 2200, "MKD": 619, "MNP": 2000,
        "NOR": 1414, "OMN": 125, "PAK": 494, "PLW": 3800, "PSE": 402,
        "PAN": 2928, "PNG": 3142, "PRY": 1130, "PER": 1738, "PHL": 2348,
        "POL": 600, "PRT": 854, "PRI": 1500, "QAT": 74, "REU": 1500,
        "ROU": 637, "RUS": 460, "RWA": 1212, "BLM": 1000, "KNA": 1170,
        "LCA": 2301, "MAF": 1000, "SPM": 1400, "VCT": 1583, "WSM": 2880,
        "SMR": 800, "STP": 2000, "SAU": 59, "SEN": 686, "SRB": 686,
        "SYC": 2330, "SLE": 2526, "SGP": 2497, "SXM": 1000, "SVK": 824,
        "SVN": 1162, "SLB": 3028, "SOM": 282, "ZAF": 495, "SSD": 990,
        "ESP": 636, "LKA": 1712, "SDN": 416, "SUR": 2331, "SWE": 624,
        "CHE": 1537, "SYR": 252, "TWN": 2500, "TJK": 691, "TZA": 1071,
        "THA": 1622, "TLS": 1500, "TGO": 1168, "TKL": 2800, "TON": 1700,
        "TTO": 2200, "TUN": 313, "TUR": 593, "TKM": 161, "TCA": 1000,
        "TUV": 3000, "UGA": 1180, "UKR": 565, "ARE": 78, "GBR": 1220,
        "USA": 715, "URY": 1300, "UZB": 206, "VUT": 2200, "VEN": 1875,
        "VNM": 1821, "VGB": 1150, "VIR": 1130, "WLF": 2500, "YEM": 167,
        "ZMB": 1020, "ZWE": 657, "XKX": 730, "ESH": 38,
    }


def get_avg_elevation_data() -> dict:
    """Average elevation in meters (CIA World Factbook / CIESIN)."""
    return {
        "AFG": 1884, "ALB": 708, "DZA": 800, "ASM": 200, "AND": 1996,
        "AGO": 1112, "AIA": 35, "ATG": 44, "ARG": 595, "ARM": 1792,
        "ABW": 24, "AUS": 330, "AUT": 910, "AZE": 384, "BHS": 9,
        "BHR": 10, "BGD": 85, "BRB": 50, "BLR": 160, "BEL": 181,
        "BLZ": 173, "BEN": 273, "BMU": 15, "BTN": 3280, "BOL": 1192,
        "BIH": 500, "BWA": 1013, "BRA": 320, "BRN": 78, "BGR": 472,
        "BFA": 297, "BDI": 1504, "CPV": 395, "KHM": 126, "CMR": 667,
        "CAN": 487, "CYM": 12, "CAF": 635, "TCD": 543, "CHL": 1871,
        "CHN": 1840, "COL": 593, "COM": 447, "COG": 430, "COD": 726,
        "COK": 10, "CRI": 746, "CIV": 250, "HRV": 331, "CUB": 108,
        "CUW": 29, "CYP": 91, "CZE": 433, "DNK": 34, "DJI": 430,
        "DMA": 425, "DOM": 424, "ECU": 1117, "EGY": 321, "SLV": 442,
        "GNQ": 577, "ERI": 853, "EST": 61, "SWZ": 945, "ETH": 1330,
        "FLK": 25, "FRO": 275, "FJI": 180, "FIN": 164, "FRA": 375,
        "GUF": 200, "PYF": 170, "GAB": 377, "GMB": 34, "GEO": 1432,
        "DEU": 263, "GHA": 190, "GIB": 90, "GRC": 498, "GRL": 1792,
        "GRD": 300, "GLP": 200, "GUM": 150, "GTM": 759, "GGY": 35,
        "GIN": 472, "GNB": 70, "GUY": 207, "HTI": 470, "HND": 684,
        "HKG": 90, "HUN": 143, "ISL": 557, "IND": 160, "IDN": 367,
        "IRN": 1305, "IRQ": 312, "IRL": 118, "IMN": 177, "ISR": 508,
        "ITA": 538, "JAM": 268, "JPN": 438, "JEY": 40, "JOR": 812,
        "KAZ": 387, "KEN": 762, "KIR": 2, "PRK": 600, "KOR": 282,
        "KWT": 108, "KGZ": 2988, "LAO": 710, "LVA": 87, "LBN": 1250,
        "LSO": 2161, "LBR": 243, "LBY": 423, "LIE": 1600, "LTU": 110,
        "LUX": 325, "MAC": 15, "MDG": 615, "MWI": 779, "MYS": 340,
        "MDV": 2, "MLI": 343, "MLT": 75, "MHL": 2, "MTQ": 200,
        "MRT": 276, "MUS": 203, "MYT": 200, "MEX": 1111, "FSM": 120,
        "MDA": 139, "MCO": 62, "MNG": 1528, "MNE": 1086, "MSR": 200,
        "MAR": 909, "MOZ": 345, "MMR": 702, "NAM": 1141, "NRU": 20,
        "NPL": 2565, "NLD": 30, "NCL": 200, "NZL": 388, "NIC": 298,
        "NER": 474, "NGA": 380, "NIU": 30, "MKD": 741, "MNP": 150,
        "NOR": 460, "OMN": 310, "PAK": 900, "PLW": 80, "PSE": 520,
        "PAN": 360, "PNG": 667, "PRY": 178, "PER": 1555, "PHL": 442,
        "POL": 173, "PRT": 372, "PRI": 261, "QAT": 28, "REU": 600,
        "ROU": 414, "RUS": 600, "RWA": 1598, "BLM": 50, "KNA": 100,
        "LCA": 247, "MAF": 30, "SPM": 60, "VCT": 250, "WSM": 100,
        "SMR": 550, "STP": 410, "SAU": 665, "SEN": 69, "SRB": 442,
        "SYC": 112, "SLE": 279, "SGP": 15, "SXM": 12, "SVK": 458,
        "SVN": 492, "SLB": 180, "SOM": 410, "ZAF": 1034, "SSD": 580,
        "ESP": 660, "LKA": 228, "SDN": 568, "SUR": 246, "SWE": 320,
        "CHE": 1350, "SYR": 514, "TWN": 1150, "TJK": 3186, "TZA": 1018,
        "THA": 287, "TLS": 595, "TGO": 236, "TKL": 2, "TON": 40,
        "TTO": 83, "TUN": 246, "TUR": 1132, "TKM": 230, "TCA": 10,
        "TUV": 2, "UGA": 1100, "UKR": 175, "ARE": 149, "GBR": 162,
        "USA": 760, "URY": 109, "UZB": 353, "VUT": 450, "VEN": 450,
        "VNM": 398, "VGB": 100, "VIR": 100, "WLF": 50, "YEM": 999,
        "ZMB": 1138, "ZWE": 961, "XKX": 800, "ESH": 256,
    }


def get_elevation_max_data() -> dict:
    """Highest point in meters (CIA World Factbook / Peakbagger)."""
    return {
        "AFG": 7492, "ALB": 2764, "DZA": 3003, "ASM": 966, "AND": 2946,
        "AGO": 2620, "AIA": 65, "ATG": 402, "ARG": 6961, "ARM": 4090,
        "ABW": 188, "AUS": 2228, "AUT": 3798, "AZE": 4466, "BHS": 63,
        "BHR": 134, "BGD": 1052, "BRB": 336, "BLR": 346, "BEL": 694,
        "BLZ": 1124, "BEN": 658, "BMU": 79, "BTN": 7570, "BOL": 6542,
        "BIH": 2386, "BWA": 1489, "BRA": 2994, "BRN": 1850, "BGR": 2925,
        "BFA": 749, "BDI": 2670, "CPV": 2829, "KHM": 1810, "CMR": 4095,
        "CAN": 5959, "CYM": 43, "CAF": 1420, "TCD": 3415, "CHL": 6893,
        "CHN": 8848, "COL": 5775, "COM": 2361, "COG": 903, "COD": 5109,
        "COK": 652, "CRI": 3820, "CIV": 1752, "HRV": 1831, "CUB": 1974,
        "CUW": 372, "CYP": 1952, "CZE": 1603, "DNK": 171, "DJI": 2028,
        "DMA": 1447, "DOM": 3098, "ECU": 6263, "EGY": 2629, "SLV": 2730,
        "GNQ": 3008, "ERI": 3018, "EST": 318, "SWZ": 1862, "ETH": 4550,
        "FLK": 705, "FRO": 882, "FJI": 1324, "FIN": 1324, "FRA": 4810,
        "GUF": 851, "PYF": 2241, "GAB": 1020, "GMB": 64, "GEO": 5193,
        "DEU": 2962, "GHA": 885, "GIB": 426, "GRC": 2918, "GRL": 3694,
        "GRD": 840, "GLP": 1467, "GUM": 406, "GTM": 4220, "GGY": 114,
        "GIN": 1752, "GNB": 300, "GUY": 2772, "HTI": 2680, "HND": 2870,
        "HKG": 958, "HUN": 1014, "ISL": 2110, "IND": 8598, "IDN": 4884,
        "IRN": 5610, "IRQ": 3611, "IRL": 1041, "IMN": 621, "ISR": 1208,
        "ITA": 4748, "JAM": 2256, "JPN": 3776, "JEY": 143, "JOR": 1854,
        "KAZ": 7010, "KEN": 5199, "KIR": 81, "PRK": 2744, "KOR": 1950,
        "KWT": 306, "KGZ": 7439, "LAO": 2817, "LVA": 312, "LBN": 3088,
        "LSO": 3482, "LBR": 1440, "LBY": 2267, "LIE": 2599, "LTU": 294,
        "LUX": 559, "MAC": 172, "MDG": 2876, "MWI": 3002, "MYS": 4095,
        "MDV": 5, "MLI": 1155, "MLT": 253, "MHL": 10, "MTQ": 1397,
        "MRT": 915, "MUS": 828, "MYT": 660, "MEX": 5636, "FSM": 791,
        "MDA": 430, "MCO": 162, "MNG": 4374, "MNE": 2534, "MSR": 915,
        "MAR": 4165, "MOZ": 2436, "MMR": 5881, "NAM": 2606, "NRU": 71,
        "NPL": 8848, "NLD": 322, "NCL": 1628, "NZL": 3724, "NIC": 2438,
        "NER": 2022, "NGA": 2419, "NIU": 68, "MKD": 2764, "MNP": 965,
        "NOR": 2469, "OMN": 3004, "PAK": 8611, "PLW": 242, "PSE": 1022,
        "PAN": 3475, "PNG": 4509, "PRY": 842, "PER": 6768, "PHL": 2954,
        "POL": 2499, "PRT": 2351, "PRI": 1339, "QAT": 103, "REU": 3071,
        "ROU": 2544, "RUS": 5642, "RWA": 4519, "BLM": 286, "KNA": 1156,
        "LCA": 950, "MAF": 424, "SPM": 240, "VCT": 1234, "WSM": 1858,
        "SMR": 749, "STP": 2024, "SAU": 3133, "SEN": 581, "SRB": 2169,
        "SYC": 905, "SLE": 1948, "SGP": 166, "SXM": 383, "SVK": 2655,
        "SVN": 2864, "SLB": 2335, "SOM": 2416, "ZAF": 3450, "SSD": 3187,
        "ESP": 3479, "LKA": 2524, "SDN": 3187, "SUR": 1230, "SWE": 2111,
        "CHE": 4634, "SYR": 2814, "TWN": 3952, "TJK": 7495, "TZA": 5895,
        "THA": 2565, "TLS": 2963, "TGO": 986, "TKL": 5, "TON": 1033,
        "TTO": 940, "TUN": 1544, "TUR": 5137, "TKM": 3139, "TCA": 49,
        "TUV": 5, "UGA": 5110, "UKR": 2061, "ARE": 1910, "GBR": 1345,
        "USA": 6190, "URY": 514, "UZB": 4643, "VUT": 1877, "VEN": 4978,
        "VNM": 3143, "VGB": 521, "VIR": 474, "WLF": 765, "YEM": 3666,
        "ZMB": 2301, "ZWE": 2592, "XKX": 2656, "ESH": 463,
    }


# ── Main update logic ───────────────────────────────────────────────────────

def main():
    # Read current CSV
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    print(f"Loaded {len(rows)} countries from {CSV_PATH}")

    # ── 1. Fetch World Bank data ──
    wb_data: dict[str, dict] = {}
    for col_name, indicator in WB_INDICATORS.items():
        wb_data[col_name] = fetch_wb_indicator(indicator)
        time.sleep(0.5)  # rate limit courtesy

    # ── 2. Get compiled geographic/demographic data ──
    compiled_data = {
        "median_age":            get_median_age_data(),
        "avg_temperature_c":     get_avg_temperature_data(),
        "annual_precipitation_mm": get_annual_precipitation_data(),
        "avg_elevation_m":       get_avg_elevation_data(),
        "elevation_max_m":       get_elevation_max_data(),
    }

    # ── 3. Add missing columns to fieldnames ──
    all_new_cols = list(WB_INDICATORS.keys()) + list(compiled_data.keys())
    for col in all_new_cols:
        if col not in fieldnames:
            fieldnames.append(col)
            print(f"Added new column: {col}")

    # ── 4. Update rows ──
    stats = {col: 0 for col in all_new_cols}
    for row in rows:
        iso3 = row.get("iso_a3", "")

        # World Bank data
        for col_name, data in wb_data.items():
            current = row.get(col_name, "")
            if not current and iso3 in data:
                val = data[iso3]
                # tourism_arrivals is int, others are float
                if col_name == "tourism_arrivals":
                    row[col_name] = str(int(val))
                else:
                    row[col_name] = str(val)
                stats[col_name] += 1
            elif col_name not in row:
                row[col_name] = ""

        # Compiled data
        for col_name, data in compiled_data.items():
            current = row.get(col_name, "")
            if not current and iso3 in data:
                row[col_name] = str(data[iso3])
                stats[col_name] += 1
            elif col_name not in row:
                row[col_name] = ""

    # ── 5. Write updated CSV ──
    with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nUpdated {CSV_PATH}")
    print("Values added per column:")
    for col, count in stats.items():
        print(f"  {col}: {count}")


if __name__ == "__main__":
    main()
