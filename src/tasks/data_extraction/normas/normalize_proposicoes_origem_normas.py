import json
from tqdm import tqdm
import re


MAPA_SIGLAS = {
    "Proposta de Emenda à Constituição": "PEC",
    "Medida Provisória": "MPV",
    "Projeto de Resolução do Congresso Nacional": "PRN",
    "Projeto de Resolução do Senado": "PRS",
    "Projeto de Lei do Senado": "PLS",
    "Projeto de Decreto Legislativo (SF)": "PDS",
    "Projeto de Decreto Legislativo (CD)": "PDC",
    "Projeto de Decreto Legislativo (CN)": "PDN",
    "Projeto de Decreto Legislativo": "PDL",
    "Projeto de Lei da Câmara": "PLC",
    "Projeto de Lei (CD)": "PL",
    "Projeto de Lei do Congresso Nacional": "PLN",
    "Projeto de Lei de Conversão (CN)": "PLV",
    "Projeto Lei Complementar (CD)": "PLP",
    "Projeto de Lei": "PL",
    "Projeto de Lei Complementar": "PLP",
    "Veto": "VET",
    "Substitutivo da Câmara dos Deputados a Projeto de Lei do Senado": "SCD",
    "Emenda(s) da Câmara dos Deputados a Projeto de Lei do Senado": "ECD"
}

MAPA_CASAS = {
    "Projeto de Lei do Senado": "SF",
    "Projeto de Lei da Câmara": "SF",
    "Projeto de Lei (CD)": "CD",
    "Projeto Lei Complementar (CD)": "CD",
    "Projeto de Decreto Legislativo (CD)": "CD",
    "Projeto de Decreto Legislativo (SF)": "SF",

}


def extract_origin_from_lexml(text: str):

    if not text:
        return None

    origin = re.findall(r'\[([^\]]+)\]', text)

    if origin:

        origin = origin[0].strip()

        return [
            item.strip()
            for item in origin.split(":", 1)[0].split(">")
        ]

    return None

def extract_origin_from_normas_leg_br(text: str):
    if text:
        return [
            item.strip()
            for item in text.split(":", 1)[0].split(">")
        ]
    return None

def normalize_origin(origins, urn=None):

    if not origins:
        return None, None

    normalized = []
    casas = []

    for origin in origins:

        tipo_match = re.match(r"^(.*?) nº", origin)

        if not tipo_match:
            print("----------------------------", origin)
            #normalized.append(origin)
            #casas.append(None)
            continue
        
        if urn and "lei.complementar" in urn and origin.startswith("Projeto de Lei (CD)"):
            sigla = "PLP"
            tipo = "Projeto Lei Complementar (CD)"
        else:
            tipo = tipo_match.group(1).strip()

            sigla = MAPA_SIGLAS.get(tipo)

        origin = re.sub(r'(\d+)E/(\d+)', r'\1/\2', origin)
        numero_match = re.search(r"(\d+A?/\d+)", origin)

        if sigla and numero_match:
            normalized.append(
                f"{sigla} {numero_match.group(1)}"
            )
            if MAPA_CASAS.get(tipo):
                casas.append(MAPA_CASAS.get(tipo))
            else:
                casas.append(None)
        else:
            print(origin)
            normalized.append(origin)
            casas.append(None)

    return normalized, casas


with open(
    "data/normas/metadados/normas.json",
    "r",
    encoding="utf-8"
) as f:
    normas = json.load(f)

with open(
    "data/normas/metadados/proposicoes_de_origem_da_norma_from_normas_leg_br.json",
    "r",
    encoding="utf-8"
) as f:
    origens_normas_leg_br = json.load(f)

with open("data/normas/metadados/proposicoes_de_origem_da_norma_from_sf.json", "r", encoding="utf-8") as f:
    origens_sf = json.load(f)

with open("data/normas/metadados/projetos_resolucao_cd_transf_norma.json", "r", encoding="utf-8") as f:
    prcs_transf_norma = json.load(f)

origens_normas_leg_br_map = {
    item["urn"]: item.get("sourceProcess")
    for item in origens_normas_leg_br
}

origens_sf_map = {
    item["urn"]: item.get("resultado")[0].get("identificacao")
    for item in origens_sf if item.get("resultado")
}

def normalizar_resolucao_cd(titulo):
    match = re.match(
        r"(Resolução da Câmara dos Deputados)\s*n[ºo]\s*(\d+),\s*de\s*(\d{4})",
        titulo
    )

    if match:
        prefixo, numero, ano = match.groups()
        return f"{prefixo} {numero}/{ano}"

    return titulo

prcs_map = {
    item["nome_norma"]: item["nomeProposicao"]
    for item in prcs_transf_norma
}

origens = {}
x = 0
for norma in tqdm(normas):

    origem_cd_norm = None
    if norma["titulo"].startswith("Resolução da Câmara dos Deputados"):
        #print(norma)
        origem_cd = prcs_map.get(normalizar_resolucao_cd(norma["titulo"]))
        if not origem_cd:
            x += 1
            print("Não encontrado na PRC:", norma["titulo"])
            continue
        else:
            origem_cd_norm = [origem_cd]
            casas_cd = ["CD"]

    urn = norma.get("urn")

    origem_lexml = norma.get("relacionamentos")

    origem_normas = None

    if origens_normas_leg_br_map.get(urn):

        origem_normas = (
            origens_normas_leg_br_map
            .get(urn, {})
            .get("name")
        )

    origem_sf = None
    origem_sf_norm = None
    if not origem_lexml and not origem_normas and not origem_cd_norm:
        origem_sf = origens_sf_map.get(urn)
        if not origem_sf:
            print("URN sem origens:", urn)
            x += 1
            continue
        origem_sf_norm = [origem_sf]
        casas_sf = [None]

    origem_lexml_extraida = extract_origin_from_lexml(
        origem_lexml
    )

    origem_lexml_norm, casas_lexml = normalize_origin(
        origem_lexml_extraida, urn
    )

    origem_normas_leg_br_extraida = extract_origin_from_normas_leg_br(
        origem_normas
    )

    origem_normas_leg_br_norm, casas_normas_leg_br = normalize_origin(
        origem_normas_leg_br_extraida, urn
    )

    origens[urn] = {
        "origem_lexml": origem_lexml,
        "origem_lexml_norm": origem_lexml_norm,
        "origem_normas.leg.br": origem_normas,
        "origem_normas.leg.br_norm": origem_normas_leg_br_norm,
        "origem_sf": origem_sf,
        "origem_sf_norm": origem_sf_norm,
        "origem_final": origem_normas_leg_br_norm or origem_lexml_norm or origem_sf_norm or origem_cd_norm,
        "casas": casas_normas_leg_br or casas_lexml  or casas_sf or casas_cd
    }

with open(
    "data/normas/metadados/proposicoes_origem_normalizadas.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        origens,
        f,
        indent=4,
        ensure_ascii=False
    )

print("Total consolidado:", len(origens))
print("Não encontrado:", x)