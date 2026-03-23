"""Add name_es, name_official_es, capital_es, and entity_type columns to countries.csv."""

import csv
import os

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "data", "countries.csv")

# ISO A3 → Spanish name
NAMES_ES = {
    "AFG": "Afganistán", "ALB": "Albania", "DZA": "Argelia", "ASM": "Samoa Americana",
    "AND": "Andorra", "AGO": "Angola", "AIA": "Anguila", "ATA": "Antártida",
    "ATG": "Antigua y Barbuda", "ARG": "Argentina", "ARM": "Armenia", "ABW": "Aruba",
    "AUS": "Australia", "AUT": "Austria", "AZE": "Azerbaiyán", "BHS": "Bahamas",
    "BHR": "Baréin", "BGD": "Bangladés", "BRB": "Barbados", "BLR": "Bielorrusia",
    "BEL": "Bélgica", "BLZ": "Belice", "BEN": "Benín", "BMU": "Bermudas",
    "BTN": "Bután", "BOL": "Bolivia", "BIH": "Bosnia y Herzegovina", "BWA": "Botsuana",
    "BRA": "Brasil", "IOT": "Territorio Británico del Océano Índico",
    "VGB": "Islas Vírgenes Británicas", "BRN": "Brunéi", "BGR": "Bulgaria",
    "BFA": "Burkina Faso", "BDI": "Burundi", "CPV": "Cabo Verde", "KHM": "Camboya",
    "CMR": "Camerún", "CAN": "Canadá", "CYM": "Islas Caimán", "CAF": "República Centroafricana",
    "TCD": "Chad", "CHL": "Chile", "CHN": "China", "CXR": "Isla de Navidad",
    "CCK": "Islas Cocos", "COL": "Colombia", "COM": "Comoras", "COG": "República del Congo",
    "COD": "República Democrática del Congo", "COK": "Islas Cook", "CRI": "Costa Rica",
    "CIV": "Costa de Marfil", "HRV": "Croacia", "CUB": "Cuba", "CUW": "Curazao",
    "CYP": "Chipre", "CZE": "Chequia", "DNK": "Dinamarca", "DJI": "Yibuti",
    "DMA": "Dominica", "DOM": "República Dominicana", "ECU": "Ecuador", "EGY": "Egipto",
    "SLV": "El Salvador", "GNQ": "Guinea Ecuatorial", "ERI": "Eritrea", "EST": "Estonia",
    "SWZ": "Esuatini", "ETH": "Etiopía", "FLK": "Islas Malvinas", "FRO": "Islas Feroe",
    "FJI": "Fiyi", "FIN": "Finlandia", "FRA": "Francia", "GUF": "Guayana Francesa",
    "PYF": "Polinesia Francesa", "ATF": "Territorios Australes Franceses",
    "GAB": "Gabón", "GMB": "Gambia", "GEO": "Georgia", "DEU": "Alemania",
    "GHA": "Ghana", "GIB": "Gibraltar", "GRC": "Grecia", "GRL": "Groenlandia",
    "GRD": "Granada", "GLP": "Guadalupe", "GUM": "Guam", "GTM": "Guatemala",
    "GGY": "Guernsey", "GIN": "Guinea", "GNB": "Guinea-Bisáu", "GUY": "Guyana",
    "HTI": "Haití", "VAT": "Ciudad del Vaticano", "HND": "Honduras", "HKG": "Hong Kong",
    "HUN": "Hungría", "ISL": "Islandia", "IND": "India", "IDN": "Indonesia",
    "IRN": "Irán", "IRQ": "Irak", "IRL": "Irlanda", "IMN": "Isla de Man",
    "ISR": "Israel", "ITA": "Italia", "JAM": "Jamaica", "JPN": "Japón",
    "JEY": "Jersey", "JOR": "Jordania", "KAZ": "Kazajistán", "KEN": "Kenia",
    "KIR": "Kiribati", "PRK": "Corea del Norte", "KOR": "Corea del Sur",
    "UNK": "Kosovo", "KWT": "Kuwait", "KGZ": "Kirguistán", "LAO": "Laos",
    "LVA": "Letonia", "LBN": "Líbano", "LSO": "Lesoto", "LBR": "Liberia",
    "LBY": "Libia", "LIE": "Liechtenstein", "LTU": "Lituania", "LUX": "Luxemburgo",
    "MAC": "Macao", "MDG": "Madagascar", "MWI": "Malaui", "MYS": "Malasia",
    "MDV": "Maldivas", "MLI": "Malí", "MLT": "Malta", "MHL": "Islas Marshall",
    "MTQ": "Martinica", "MRT": "Mauritania", "MUS": "Mauricio", "MYT": "Mayotte",
    "MEX": "México", "FSM": "Micronesia", "MDA": "Moldavia", "MCO": "Mónaco",
    "MNG": "Mongolia", "MNE": "Montenegro", "MSR": "Montserrat", "MAR": "Marruecos",
    "MOZ": "Mozambique", "MMR": "Myanmar", "NAM": "Namibia", "NRU": "Nauru",
    "NPL": "Nepal", "NLD": "Países Bajos", "NCL": "Nueva Caledonia",
    "NZL": "Nueva Zelanda", "NIC": "Nicaragua", "NER": "Níger", "NGA": "Nigeria",
    "NIU": "Niue", "NFK": "Isla Norfolk", "MKD": "Macedonia del Norte",
    "MNP": "Islas Marianas del Norte", "NOR": "Noruega", "OMN": "Omán",
    "PAK": "Pakistán", "PLW": "Palaos", "PSE": "Palestina", "PAN": "Panamá",
    "PNG": "Papúa Nueva Guinea", "PRY": "Paraguay", "PER": "Perú", "PHL": "Filipinas",
    "PCN": "Islas Pitcairn", "POL": "Polonia", "PRT": "Portugal", "PRI": "Puerto Rico",
    "QAT": "Catar", "REU": "Reunión", "ROU": "Rumanía", "RUS": "Rusia",
    "RWA": "Ruanda", "BLM": "San Bartolomé", "SHN": "Santa Elena",
    "KNA": "San Cristóbal y Nieves", "LCA": "Santa Lucía", "MAF": "San Martín",
    "SPM": "San Pedro y Miquelón", "VCT": "San Vicente y las Granadinas",
    "WSM": "Samoa", "SMR": "San Marino", "STP": "Santo Tomé y Príncipe",
    "SAU": "Arabia Saudita", "SEN": "Senegal", "SRB": "Serbia", "SYC": "Seychelles",
    "SLE": "Sierra Leona", "SGP": "Singapur", "SXM": "Sint Maarten",
    "SVK": "Eslovaquia", "SVN": "Eslovenia", "SLB": "Islas Salomón", "SOM": "Somalia",
    "ZAF": "Sudáfrica", "SGS": "Georgia del Sur", "SSD": "Sudán del Sur",
    "ESP": "España", "LKA": "Sri Lanka", "SDN": "Sudán", "SUR": "Surinam",
    "SJM": "Svalbard y Jan Mayen", "SWE": "Suecia", "CHE": "Suiza",
    "SYR": "Siria", "TWN": "Taiwán", "TJK": "Tayikistán", "TZA": "Tanzania",
    "THA": "Tailandia", "TLS": "Timor Oriental", "TGO": "Togo", "TKL": "Tokelau",
    "TON": "Tonga", "TTO": "Trinidad y Tobago", "TUN": "Túnez", "TUR": "Turquía",
    "TKM": "Turkmenistán", "TCA": "Islas Turcas y Caicos", "TUV": "Tuvalu",
    "UGA": "Uganda", "UKR": "Ucrania", "ARE": "Emiratos Árabes Unidos",
    "GBR": "Reino Unido", "USA": "Estados Unidos", "UMI": "Islas Ultramarinas de EE. UU.",
    "VIR": "Islas Vírgenes de EE. UU.", "URY": "Uruguay", "UZB": "Uzbekistán",
    "VUT": "Vanuatu", "VEN": "Venezuela", "VNM": "Vietnam",
    "WLF": "Wallis y Futuna", "ESH": "Sáhara Occidental", "YEM": "Yemen",
    "ZMB": "Zambia", "ZWE": "Zimbabue", "ALA": "Islas Åland",
}

# Capitals in Spanish (only those that differ from English)
CAPITALS_ES = {
    "AFG": "Kabul", "ALB": "Tirana", "DZA": "Argel", "AND": "Andorra la Vieja",
    "AGO": "Luanda", "ATG": "Saint John's", "ARG": "Buenos Aires", "ARM": "Ereván",
    "AUS": "Canberra", "AUT": "Viena", "AZE": "Bakú", "BHS": "Nasáu",
    "BHR": "Manama", "BGD": "Daca", "BRB": "Bridgetown", "BLR": "Minsk",
    "BEL": "Bruselas", "BLZ": "Belmopán", "BEN": "Porto Novo", "BTN": "Timbu",
    "BOL": "Sucre", "BIH": "Sarajevo", "BWA": "Gaborone", "BRA": "Brasilia",
    "BRN": "Bandar Seri Begawan", "BGR": "Sofía", "BFA": "Uagadugú", "BDI": "Gitega",
    "CPV": "Praia", "KHM": "Nom Pen", "CMR": "Yaundé", "CAN": "Ottawa",
    "CAF": "Bangui", "TCD": "Yamena", "CHL": "Santiago", "CHN": "Pekín",
    "COL": "Bogotá", "COM": "Moroni", "COG": "Brazzaville",
    "COD": "Kinsasa", "CRI": "San José", "CIV": "Yamusukro",
    "HRV": "Zagreb", "CUB": "La Habana", "CYP": "Nicosia", "CZE": "Praga",
    "DNK": "Copenhague", "DJI": "Yibuti", "DMA": "Roseau",
    "DOM": "Santo Domingo", "ECU": "Quito", "EGY": "El Cairo",
    "SLV": "San Salvador", "GNQ": "Malabo", "ERI": "Asmara", "EST": "Tallin",
    "SWZ": "Mbabane", "ETH": "Adís Abeba", "FJI": "Suva", "FIN": "Helsinki",
    "FRA": "París", "GAB": "Libreville", "GMB": "Banjul", "GEO": "Tiflis",
    "DEU": "Berlín", "GHA": "Acra", "GRC": "Atenas", "GRD": "Saint George's",
    "GTM": "Ciudad de Guatemala", "GIN": "Conakri", "GNB": "Bisáu",
    "GUY": "Georgetown", "HTI": "Puerto Príncipe", "VAT": "Ciudad del Vaticano",
    "HND": "Tegucigalpa", "HUN": "Budapest", "ISL": "Reikiavik", "IND": "Nueva Delhi",
    "IDN": "Yakarta", "IRN": "Teherán", "IRQ": "Bagdad", "IRL": "Dublín",
    "ISR": "Jerusalén", "ITA": "Roma", "JAM": "Kingston", "JPN": "Tokio",
    "JOR": "Amán", "KAZ": "Astaná", "KEN": "Nairobi", "KIR": "Tarawa Sur",
    "PRK": "Pionyang", "KOR": "Seúl", "KWT": "Ciudad de Kuwait",
    "KGZ": "Biskek", "LAO": "Vientián", "LVA": "Riga", "LBN": "Beirut",
    "LSO": "Maseru", "LBR": "Monrovia", "LBY": "Trípoli", "LIE": "Vaduz",
    "LTU": "Vilna", "LUX": "Luxemburgo", "MDG": "Antananarivo", "MWI": "Lilongüe",
    "MYS": "Kuala Lumpur", "MDV": "Malé", "MLI": "Bamako", "MLT": "La Valeta",
    "MHL": "Majuro", "MRT": "Nuakchot", "MUS": "Port Louis", "MEX": "Ciudad de México",
    "FSM": "Palikir", "MDA": "Chisináu", "MCO": "Mónaco", "MNG": "Ulán Bator",
    "MNE": "Podgorica", "MAR": "Rabat", "MOZ": "Maputo", "MMR": "Naipyidó",
    "NAM": "Windhoek", "NRU": "Yaren", "NPL": "Katmandú", "NLD": "Ámsterdam",
    "NZL": "Wellington", "NIC": "Managua", "NER": "Niamey", "NGA": "Abuya",
    "MKD": "Skopie", "NOR": "Oslo", "OMN": "Mascate", "PAK": "Islamabad",
    "PLW": "Ngerulmud", "PSE": "Ramala", "PAN": "Ciudad de Panamá",
    "PNG": "Port Moresby", "PRY": "Asunción", "PER": "Lima", "PHL": "Manila",
    "POL": "Varsovia", "PRT": "Lisboa", "QAT": "Doha", "ROU": "Bucarest",
    "RUS": "Moscú", "RWA": "Kigali", "KNA": "Basseterre", "LCA": "Castries",
    "VCT": "Kingstown", "WSM": "Apia", "SMR": "San Marino",
    "STP": "Santo Tomé", "SAU": "Riad", "SEN": "Dakar", "SRB": "Belgrado",
    "SYC": "Victoria", "SLE": "Freetown", "SGP": "Singapur", "SVK": "Bratislava",
    "SVN": "Liubliana", "SLB": "Honiara", "SOM": "Mogadiscio", "ZAF": "Pretoria",
    "SSD": "Yuba", "ESP": "Madrid", "LKA": "Sri Jayawardenepura Kotte",
    "SDN": "Jartum", "SUR": "Paramaribo", "SWE": "Estocolmo", "CHE": "Berna",
    "SYR": "Damasco", "TWN": "Taipéi", "TJK": "Dusambé", "TZA": "Dodoma",
    "THA": "Bangkok", "TLS": "Dili", "TGO": "Lomé", "TON": "Nukualofa",
    "TTO": "Puerto España", "TUN": "Túnez", "TUR": "Ankara",
    "TKM": "Asjabad", "TUV": "Funafuti", "UGA": "Kampala", "UKR": "Kiev",
    "ARE": "Abu Dabi", "GBR": "Londres", "USA": "Washington D.C.",
    "URY": "Montevideo", "UZB": "Taskent", "VUT": "Port Vila",
    "VEN": "Caracas", "VNM": "Hanói", "YEM": "Saná", "ZMB": "Lusaka",
    "ZWE": "Harare",
}


def main():
    rows = []
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        for row in reader:
            rows.append(row)

    # Add new columns
    new_fields = []
    if "name_es" not in fieldnames:
        idx = fieldnames.index("name") + 1
        fieldnames.insert(idx, "name_es")
        new_fields.append("name_es")
    if "capital_es" not in fieldnames:
        idx = fieldnames.index("capital") + 1
        fieldnames.insert(idx, "capital_es")
        new_fields.append("capital_es")
    if "entity_type" not in fieldnames:
        fieldnames.append("entity_type")
        new_fields.append("entity_type")

    for row in rows:
        iso = row["iso_a3"]
        # Spanish name
        if "name_es" in new_fields:
            row["name_es"] = NAMES_ES.get(iso, row["name"])
        # Spanish capital
        if "capital_es" in new_fields:
            row["capital_es"] = CAPITALS_ES.get(iso, row.get("capital", ""))
        # Entity type: 'country' if independent=True, 'territory' otherwise
        if "entity_type" in new_fields:
            indep = row.get("independent", "").strip()
            row["entity_type"] = "country" if indep == "True" else "territory"

    with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Report
    countries = sum(1 for r in rows if r.get("entity_type") == "country")
    territories = sum(1 for r in rows if r.get("entity_type") == "territory")
    missing_es = [r["iso_a3"] for r in rows if r.get("name_es") == r["name"] and r["iso_a3"] in NAMES_ES]
    print(f"Done: {len(rows)} entries ({countries} countries, {territories} territories)")
    print(f"Spanish names mapped: {sum(1 for r in rows if r.get('name_es') != r['name'])}")
    if missing_es:
        print(f"Name unchanged (same in EN/ES): {missing_es}")
    # Show entries without Spanish translation
    no_es = [f"{r['iso_a3']}={r['name']}" for r in rows if r["iso_a3"] not in NAMES_ES]
    if no_es:
        print(f"No ES mapping ({len(no_es)}): {', '.join(no_es)}")


if __name__ == "__main__":
    main()
