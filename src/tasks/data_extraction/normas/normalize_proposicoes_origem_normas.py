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
    "Projeto de Lei Complementar do Senado": "SF",
    "Projeto de Lei da Câmara": "SF",
    "Projeto de Lei (CD)": "CD",
    "Projeto Lei Complementar (CD)": "CD",
    "Projeto de Decreto Legislativo (CD)": "CD",
    "Projeto de Decreto Legislativo (SF)": "SF",
    "Veto": "CN",
    "Substitutivo da Câmara dos Deputados a Projeto de Lei do Senado": "SF"
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
        # 1. Remove ponto de separador de milhar (ex: 1.050/2013 -> 1050/2013)
        origin_clean = re.sub(r"(\d+)\.(\d+)", r"\1\2", origin)

        # 2. Trata erros de codificação de 'E/' caso existam pontualmente
        origin_clean = re.sub(r"(\d+)[E|e]/(\d+)", r"\1/\2", origin_clean)

        tipo_match = re.match(r"^(.*?) nº", origin_clean)

        if not tipo_match:
            continue

        if (
            urn
            and "lei.complementar" in urn
            and origin_clean.startswith("Projeto de Lei (CD)")
        ):
            sigla = "PLP"
            tipo = "Projeto Lei Complementar (CD)"
        elif "Projeto de Lei Complementar" in origin_clean and ("(Substitutivo-CD)" in origin_clean):
            sigla = "PLP"
            tipo = "Projeto de Lei Complementar do Senado"
        elif "Projeto de Lei" in origin_clean and ("(Substitutivo-CD)" in origin_clean):
            sigla = "PL"
            tipo = "Projeto de Lei do Senado"
        else:
            tipo = tipo_match.group(1).strip()
            sigla = MAPA_SIGLAS.get(tipo)

        # Captura número e ano (ex: 1050/2013 ou 1050A/2013)
        numero_match = re.search(r"(\d+[A-Za-z]?/\d{4})", origin_clean)

        if sigla and numero_match:
            normalized.append(f"{sigla} {numero_match.group(1)}")
            casas.append(MAPA_CASAS.get(tipo, None))
        else:
            normalized.append(origin_clean)
            casas.append(None)

    return (normalized if normalized else None), (casas if casas else None)



import re


def normalizar_numero(numero):
    if numero is None:
        return ""
    numero = str(numero).strip()
    numero = re.sub(r"(?<=\d)\.(?=\d)", "", numero)
    m = re.fullmatch(r"0*(\d+)([A-Za-z]*)", numero)
    if m:
        return f"{int(m.group(1))}{m.group(2)}"
    return numero


def extract_origin_from_sf(dados_ou_resposta, incluir_vetos=True):
    if isinstance(dados_ou_resposta, dict):
        itens = dados_ou_resposta.get("resultado", [dados_ou_resposta])
    elif isinstance(dados_ou_resposta, list):
        itens = dados_ou_resposta
    else:
        return []

    if not itens:
        return []

    # --- PASSO 1: Descobrir o início e a Casa Iniciadora (Tratando Nulos e Normalizando) ---
    primeiro_no = itens[0]
    identificacao_inicial = primeiro_no.get("identificacaoProcessoInicial")
    casa_iniciadora = primeiro_no.get("siglaCasaIniciadora")
    objetivo = primeiro_no.get("objetivo")

    if not identificacao_inicial:
        identificacao_inicial = primeiro_no.get("identificacao")
        casa_iniciadora = primeiro_no.get("casaIdentificadora") or "CN"

    # Aplica a normalização de pontos na proposição inicial
    if identificacao_inicial:
        identificacao_inicial = re.sub(
            r"(?<=\d)\.(?=\d)", "", identificacao_inicial
        )

    nasceu_no_sf_ou_cn = (
        casa_iniciadora in ("SF", "CN")
        or objetivo == "Iniciadora"
        or objetivo is None
    )

    # --- PASSO 2: Coletar nós da CD em outrosNumeros sem duplicar (via set de id) ---
    ids_cd_vistos = set()
    processos_cd = []

    for no in itens:
        outros = no.get("outrosNumeros") or []
        for outro in outros:
            casa_outro = outro.get("casaIdentificadora") or outro.get(
                "siglaEnteIdentificador"
            )
            sigla = outro.get("sigla", "")
            id_outro = outro.get("idOutroProcesso")

            if casa_outro == "CD" and sigla not in ("MSG", "MCN"):
                if id_outro and id_outro not in ids_cd_vistos:
                    ids_cd_vistos.add(id_outro)

                    num_norm = normalizar_numero(outro.get("numero"))
                    ano = outro.get("ano")

                    processos_cd.append(
                        {
                            "id": id_outro,
                            "proposicao": f"{sigla} {num_norm}/{ano}",
                            "casa": "CD",
                        }
                    )

    processos_cd.sort(key=lambda x: x["id"])

    # --- PASSO 3: Mapear os Nós Pais do Senado / Congresso (SF / CN / Vetos) ---
    processos_sf = []
    for no in itens:
        tipo_doc = no.get("tipoDocumento") or ""
        identificacao = no.get("identificacao") or ""
        casa_atual = no.get("casaIdentificadora") or "SF"

        is_veto = (
            "Veto" in tipo_doc
            or "Mensagem" in tipo_doc
            or identificacao.startswith("VET")
        )

        if identificacao and (casa_atual in ("SF", "CN") or is_veto):
            if is_veto and not incluir_vetos:
                continue

            processos_sf.append(
                {
                    "id": no.get("id", 0),
                    "proposicao": identificacao,
                    "casa": casa_atual,
                    "data": no.get("dataApresentacao")
                    or no.get("dataDeliberacao", ""),
                }
            )

    # --- PASSO 4: Intercalação segundo a regra ---
    resultado = []

    if not nasceu_no_sf_ou_cn:
        # Nasceu na CD (ex: PL 1023/2011 -> PLC 8/2013)
        if identificacao_inicial:
            resultado.append(
                {"proposicao": identificacao_inicial, "casa": casa_iniciadora}
            )

        for no_sf in processos_sf:
            item = {"proposicao": no_sf["proposicao"], "casa": no_sf["casa"]}
            if item not in resultado:
                resultado.append(item)

        for p_cd in processos_cd:
            item = {"proposicao": p_cd["proposicao"], "casa": "CD"}
            if item not in resultado:
                resultado.append(item)

    else:
        # Nasceu no SF ou CN (ex: PDN 1/2019 ou PEC 23/2007)
        idx_cd = 0
        total_cd = len(processos_cd)

        for no_sf in processos_sf:
            item = {"proposicao": no_sf["proposicao"], "casa": no_sf["casa"]}
            if item not in resultado:
                resultado.append(item)

            if idx_cd < total_cd:
                item_cd = {
                    "proposicao": processos_cd[idx_cd]["proposicao"],
                    "casa": "CD",
                }
                if item_cd not in resultado:
                    resultado.append(item_cd)
                idx_cd += 1

    return resultado


def normalize_origin_from_sf(data):
    return [o["proposicao"] for o in data], [o["casa"] for o in data]

EDGE_CASES = {"urn:lex:br:federal:lei.complementar:2019-04-08;166": 0}

def get_final_origin(*opcoes):
    """
    opcoes: pares (origens, casas)

    Escolhe a opção com maior quantidade de pares
    (origem, casa) completamente preenchidos.
    Em caso de empate, mantém a ordem de prioridade.
    """

    melhor_origem = None
    melhor_casas = None
    melhor_score = -1

    for origens, casas in opcoes:
        if not origens or not casas:
            score = 0
        else:
            score = sum(
                1
                for origem, casa in zip(origens, casas)
                if origem is not None and casa is not None
            )

        if score > melhor_score:
            melhor_score = score
            melhor_origem = origens
            melhor_casas = casas

    return melhor_origem, melhor_casas

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
    item["urn"]: item.get("resultado")
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
    casas_cd = []
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

    origem_sf = extract_origin_from_sf(origens_sf_map.get(urn, {}))

    if not origem_lexml and not origem_normas and not origem_cd_norm and not origem_sf:
        print("URN sem origens:", urn)
        x += 1
        continue


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

    origem_sf_norm, casas_sf = normalize_origin_from_sf(origem_sf)
    opcoes = [
        (origem_sf_norm, casas_sf),
        (origem_normas_leg_br_norm, casas_normas_leg_br),
        (origem_lexml_norm, casas_lexml),
        (origem_cd_norm, casas_cd)]

    if urn in EDGE_CASES:
        origem_final, casas_final = opcoes[EDGE_CASES[urn]]
    else:
        origem_final, casas_final = get_final_origin(*opcoes)
    origens[urn] = {
        "origem_lexml": origem_lexml,
        "origem_lexml_norm": origem_lexml_norm,
        "origem_normas.leg.br": origem_normas,
        "origem_normas.leg.br_norm": origem_normas_leg_br_norm,
        "origem_sf": origem_sf,
        "origem_sf_norm": origem_sf_norm,
        "origem_final": origem_final,
        "casas": casas_final
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