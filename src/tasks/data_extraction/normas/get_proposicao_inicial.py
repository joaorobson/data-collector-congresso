import json
from tqdm import tqdm
import re

with open(
    "data/normas/metadados/proposicoes_de_origem_da_norma_from_sf.json",
    "r",
    encoding="utf-8",
) as f:
    origens_sf = json.load(f)

with open(
    "data/normas/metadados/proposicoes_de_origem_da_norma_from_normas_leg_br.json",
    "r",
    encoding="utf-8",
) as f:
    origens_normas_leg_br = json.load(f)

with open("data/normas/metadados/normas.json", "r", encoding="utf-8") as f:
    normas = json.load(f)

with open(
    "data/normas/metadados/projetos_resolucao_cd_transf_norma.json",
    "r",
    encoding="utf-8",
) as f:
    prcs_transf_norma = json.load(f)

origens_sf_map = {
    item["urn"]: item.get("resultado") for item in origens_sf if item.get("resultado")
}

origens_normas_leg_br_map = {
    item["urn"]: item.get("sourceProcess") for item in origens_normas_leg_br
}

prcs_map = {item["nome_norma"]: item["nomeProposicao"] for item in prcs_transf_norma}


URNS_SEM_ORIGEM = {"urn:lex:br:federal:decreto.legislativo:2014-07-03;236": "CD"}

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
    "Emenda(s) da Câmara dos Deputados a Projeto de Lei do Senado": "ECD",
}

MAPA_CASAS = {
    "Projeto de Lei do Senado": "SF",
    "Projeto de Lei Complementar do Senado": "SF",
    "Projeto de Lei da Câmara": "SF",
    "Projeto de Lei (CD)": "CD",
    "Projeto Lei Complementar (CD)": "CD",
    "Projeto de Decreto Legislativo (CD)": "CD",
    "Projeto de Decreto Legislativo (SF)": "SF",
    "Veto": "CN",
    "Substitutivo da Câmara dos Deputados a Projeto de Lei do Senado": "SF",
}
def normalizar_resolucao_cd(titulo):
    match = re.match(
        r"(Resolução da Câmara dos Deputados)\s*n[ºo]\s*(\d+),\s*de\s*(\d{4})", titulo
    )

    if match:
        prefixo, numero, ano = match.groups()
        return f"{prefixo} {numero}/{ano}"

    return titulo

def extract_origin_from_lexml(text: str):
    if not text:
        return None

    origin = re.findall(r"\[([^\]]+)\]", text)

    if origin:
        origin = origin[0].strip()
        return [item.strip() for item in origin.split(":", 1)[0].split(">")]

    return None


def get_casa_iniciadora(urn, origens_sf_map):
    if urn in URNS_SEM_ORIGEM:
        return URNS_SEM_ORIGEM.get(urn)
    elif "camara.deputados:resolucao" in urn:
        return "CD"
    elif "senado.federal:resolucao" in urn:
        return "SF"
    elif "congresso.nacional:resolucao" in urn or (
        origens_sf_map.get(urn)
        and origens_sf_map.get(urn)[0].get("identificacao").split()[0] in ["PDN", "PDR"]
    ):
        return "CN"
    return origens_sf_map.get(urn, [{"siglaCasaIniciadora": None}])[0].get(
        "siglaCasaIniciadora"
    )

def get_first_prop(props):
    if not props:
        return None

    prop_inicial = None

    for prop in props:
        print(prop)
        origin_clean = re.sub(r"(\d+)\.(\d+)", r"\1\2", prop)
        origin_clean = re.sub(r"(\d+)[E|e]/(\d+)", r"\1/\2", origin_clean)

        tipo_match = re.match(r"^(.*?) nº", origin_clean)

        if not tipo_match:
            print(origin_clean)
            continue

        if (
            urn
            and "lei.complementar" in urn
            and origin_clean.startswith("Projeto de Lei (CD)")
        ):
            sigla = "PLP"
            tipo = "Projeto Lei Complementar (CD)"
        elif "Projeto de Lei Complementar" in origin_clean and (
            "(Substitutivo-CD)" in origin_clean
        ):
            sigla = "PLP"
            tipo = "Projeto de Lei Complementar do Senado"
        else:
            tipo = tipo_match.group(1).strip()
            sigla = MAPA_SIGLAS.get(tipo)

        numero_match = re.search(r"(\d+[A-Za-z]?/\d{4})", origin_clean)

        if sigla and numero_match:
            prop_inicial = f"{sigla} {numero_match.group(1)}"
        else:
            prop_inicial = origin_clean
        break

    return prop_inicial


urn_para_prop_inicial = {}

for norma in tqdm(normas):

    urn = norma.get("urn")
    
    if norma["titulo"].startswith("Resolução da Câmara dos Deputados"):
        prop_inicial = prcs_map.get(normalizar_resolucao_cd(norma["titulo"]))
        if not prop_inicial:
            print("Não encontrado na PRC:", norma["titulo"])
            continue
        else:
            urn_para_prop_inicial[urn] = {"proposicao": prop_inicial, "casa": "CD"}


    else:
        casa_inicial = get_casa_iniciadora(urn, origens_sf_map)
        #print(urn)
        if origens_sf_map.get(urn):
            if origens_sf_map[urn][0].get("identificacaoProcessoInicial"):
                urn_para_prop_inicial[urn] = {"proposicao": origens_sf_map[urn][0]["identificacaoProcessoInicial"], "casa": casa_inicial}
            elif "senado.federal:resolucao:" in urn or "congresso.nacional:resolucao:" in urn:
                urn_para_prop_inicial[urn] = {"proposicao": origens_sf_map[urn][0]["identificacao"], "casa": casa_inicial}
            elif "federal:decreto.legislativo:" in urn:
                identificacao = origens_sf_map[urn][0]["identificacao"]
                if identificacao.split()[0] in ["PDN", "PDR"]:
                    urn_para_prop_inicial[urn] = {"proposicao": identificacao, "casa": casa_inicial}
        if not urn_para_prop_inicial.get(urn):
            print(norma)
            origem_lexml = extract_origin_from_lexml(norma.get("relacionamentos"))
            print(origem_lexml)
            prop_inicial = get_first_prop(origem_lexml)
            print('-----', prop_inicial)
            if prop_inicial:
                urn_para_prop_inicial[urn] = {"proposicao": prop_inicial, "casa": casa_inicial}

        if origens_normas_leg_br_map.get(urn):
            origem_normas = origens_normas_leg_br_map.get(urn, {}).get("name")


for norma in normas:
    urn = norma.get("urn")
    if not urn_para_prop_inicial.get(urn):
        print(urn)

with open(
    "data/normas/metadados/proposicao_inicial.json", "w", encoding="utf-8"
) as f:
    json.dump(urn_para_prop_inicial, f, indent=4, ensure_ascii=False)