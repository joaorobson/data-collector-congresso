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


def extract_origin_from_lexml(text: str):
    if not text:
        return None

    origin = re.findall(r"\[([^\]]+)\]", text)

    if origin:
        origin = origin[0].strip()
        return [item.strip() for item in origin.split(":", 1)[0].split(">")]

    return None


def extract_origin_from_normas_leg_br(text: str):
    if text:
        return [item.strip() for item in text.split(":", 1)[0].split(">")]
    return None


def normalize_origin(casa_origem, origins, urn=None):
    if not origins:
        return None, None

    normalized = []
    casas = [casa_origem]

    for ix, origin in enumerate(origins):
        origin_clean = re.sub(r"(\d+)\.(\d+)", r"\1\2", origin)
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
        elif "Projeto de Lei Complementar" in origin_clean and (
            "(Substitutivo-CD)" in origin_clean
        ):
            sigla = "PLP"
            tipo = "Projeto de Lei Complementar do Senado"
        elif "Projeto de Lei" in origin_clean and ("(Substitutivo-CD)" in origin_clean):
            sigla = "PL"
            tipo = "Projeto de Lei do Senado"
        elif "Projeto de Lei" in origin_clean and ("(Emenda-CD)" in origin_clean):
            sigla = "PL"
            if casas[ix - 1] == "CD":
                tipo = "Projeto de Lei do Senado"
            else:
                tipo = "Projeto de Lei da Câmara"
        else:
            tipo = tipo_match.group(1).strip()
            sigla = MAPA_SIGLAS.get(tipo)

        numero_match = re.search(r"(\d+[A-Za-z]?/\d{4})", origin_clean)

        if sigla and numero_match:
            normalized.append(f"{sigla} {numero_match.group(1)}")
            if ix > 0:
                casas.append(MAPA_CASAS.get(tipo, None))
        else:
            normalized.append(origin_clean)
            if ix > 0:
                casas.append(None)

    return (normalized if normalized else None), (casas if casas else None)


URNS_SEM_ORIGEM = {"urn:lex:br:federal:decreto.legislativo:2014-07-03;236": "CD"}


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

def normalizar_numero(numero):
    if numero is None:
        return ""
    numero = str(numero).strip()
    numero = re.sub(r"(?<=\d)\.(?=\d)", "", numero)
    m = re.fullmatch(r"0*(\d+)([A-Za-z]*)", numero)
    if m:
        return f"{int(m.group(1))}{m.group(2)}"
    return numero


def extract_origin_from_sf(
    dados_ou_resposta,
    casa_origem,
    incluir_vetos=True,
):
    if isinstance(dados_ou_resposta, dict):
        itens = dados_ou_resposta.get("resultado", [dados_ou_resposta])
    elif isinstance(dados_ou_resposta, list):
        itens = dados_ou_resposta
    else:
        return []

    if not itens:
        return []

    primeiro_no = itens[0]
    objetivo_primeiro = primeiro_no.get("objetivo")

    nasceu_no_sf_ou_cn = (
        casa_origem in ("SF", "CN")
        or objetivo_primeiro == "Iniciadora"
        or objetivo_primeiro is None
    )

    resultado = []

    def adicionar_item(proposicao, casa):
        if not proposicao:
            return
        resultado.append({"proposicao": proposicao, "casa": casa})

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

        if not identificacao:
            continue

        if casa_atual not in ("SF", "CN") and not is_veto:
            continue

        if is_veto and not incluir_vetos:
            continue

        # =========================================================
        # Deduplicação estrita de outrosNumeros por nó
        # =========================================================
        outros_raw = no.get("outrosNumeros") or []
        outros_dedup = []
        ids_vistos = set()

        for outro in outros_raw:
            id_outro = outro.get("idOutroProcesso")

            if id_outro:
                if id_outro not in ids_vistos:
                    ids_vistos.add(id_outro)
                    outros_dedup.append(outro)
            else:
                sigla = outro.get("sigla", "")
                num = outro.get("numero", "")
                ano = outro.get("ano", "")
                casa_id = outro.get("casaIdentificadora") or outro.get("siglaEnteIdentificador")
                chave_unica = (sigla, num, ano, casa_id)

                if chave_unica not in ids_vistos:
                    ids_vistos.add(chave_unica)
                    outros_dedup.append(outro)

        processos_sf.append(
            {
                "id": no.get("id", 0),
                "objetivo": str(no.get("objetivo") or "").strip().capitalize(),
                "proposicao": identificacao,
                "casa": casa_atual,
                "outros_numeros": outros_dedup,
            }
        )

    # Forçar nó "Iniciadora" no topo
    processos_sf.sort(key=lambda x: 0 if x["objetivo"] == "Iniciadora" else 1)

    # PASSO 4: NASCEU NA CD
    if not nasceu_no_sf_ou_cn:
        identificacao_inicial = primeiro_no.get("identificacaoProcessoInicial") or primeiro_no.get("identificacao")
        if identificacao_inicial:
            identificacao_inicial = re.sub(r"(?<=\d)\.(?=\d)", "", identificacao_inicial)
            adicionar_item(identificacao_inicial, casa_origem)

        for no_sf in processos_sf:
            if not resultado or {"proposicao": no_sf["proposicao"], "casa": no_sf["casa"]} != resultado[0]:
                adicionar_item(proposicao=no_sf["proposicao"], casa=no_sf["casa"])

        ids_cd_vistos = set()
        for no_sf in processos_sf:
            for outro in no_sf["outros_numeros"]:
                casa_outro = outro.get("casaIdentificadora") or outro.get("siglaEnteIdentificador")
                sigla = outro.get("sigla", "")
                id_outro = outro.get("idOutroProcesso")

                if casa_outro != "CD" or sigla in ("MSG", "MCN"):
                    continue

                if id_outro and id_outro in ids_cd_vistos:
                    continue

                if id_outro:
                    ids_cd_vistos.add(id_outro)

                numero = normalizar_numero(outro.get("numero"))
                ano = outro.get("ano")

                adicionar_item(
                    proposicao=f"{sigla} {numero}/{ano}",
                    casa="CD",
                )

    # PASSO 5: NASCEU NO SF OU CN (TRAMITAÇÃO INTERCALADA)
    else:
        id_cd_ultimo_adicionado = None

        for no_sf in processos_sf:
            # 1. Adiciona o nó do SF
            adicionar_item(
                proposicao=no_sf["proposicao"],
                casa=no_sf["casa"],
            )

            # 2. Verifica a passagem correspondente na CD
            for outro in no_sf["outros_numeros"]:
                casa_outro = outro.get("casaIdentificadora") or outro.get("siglaEnteIdentificador")
                sigla = outro.get("sigla", "")

                if casa_outro != "CD" or sigla in ("MSG", "MCN"):
                    continue

                id_outro = outro.get("idOutroProcesso")
                numero = normalizar_numero(outro.get("numero"))
                ano = outro.get("ano")
                proposicao_cd = f"{sigla} {numero}/{ano}"

                chave_cd = id_outro if id_outro else proposicao_cd

                # Adiciona a CD apenas se o último elemento da CD inserido for diferente,
                # garantindo a alternância correta e evitando duplicação final em SCD.
                if chave_cd != id_cd_ultimo_adicionado:
                    adicionar_item(
                        proposicao=proposicao_cd,
                        casa="CD",
                    )
                    id_cd_ultimo_adicionado = chave_cd

                break

    return resultado


def normalize_origin_from_sf(data):
    return [o["proposicao"] for o in data], [o["casa"] for o in data]


EDGE_CASES = {"urn:lex:br:federal:lei.complementar:2019-04-08;166": 0}


def get_final_origin(origem_sf, urn):
    dados_tramitacao = fases_tramitacao.get(urn, {})

    tramitacao_urn = dados_tramitacao.get("tramitacao")
    casas = dados_tramitacao.get("casas")

    if None not in tramitacao_urn:
        return tramitacao_urn, casas

    origem_final = []

    for indice, proposicao in enumerate(tramitacao_urn):
        casa = casas[indice] if indice < len(casas) else None

        # A posição já possui um valor:
        # mantém o valor da tramitação.
        if proposicao is not None:
            origem_final.append(proposicao)
            continue

        # A posição é None e pertence à PR:
        # mantém o None.
        if casa == "PR":
            origem_final.append(None)
            continue

        # A posição é None e não pertence à PR:
        # busca o valor correspondente em origem_sf.
        if indice < len(origem_sf):
            origem_final.append(origem_sf[indice])
        else:
            origem_final.append(None)

    return origem_final, casas


# Carga de arquivos de metadados
with open("data/normas/metadados/normas.json", "r", encoding="utf-8") as f:
    normas = json.load(f)

with open(
    "data/normas/metadados/proposicoes_de_origem_da_norma_from_normas_leg_br.json",
    "r",
    encoding="utf-8",
) as f:
    origens_normas_leg_br = json.load(f)

with open(
    "data/normas/metadados/proposicoes_de_origem_da_norma_from_sf.json",
    "r",
    encoding="utf-8",
) as f:
    origens_sf = json.load(f)

with open(
    "data/normas/metadados/projetos_resolucao_cd_transf_norma.json",
    "r",
    encoding="utf-8",
) as f:
    prcs_transf_norma = json.load(f)

with open(
    "data/normas/metadados/fases_tramitacao_norm.json",
    "r",
    encoding="utf-8",
) as f:
    fases_tramitacao = json.load(f)

origens_normas_leg_br_map = {
    item["urn"]: item.get("sourceProcess") for item in origens_normas_leg_br
}

origens_sf_map = {
    item["urn"]: item.get("resultado") for item in origens_sf if item.get("resultado")
}


def normalizar_resolucao_cd(titulo):
    match = re.match(
        r"(Resolução da Câmara dos Deputados)\s*n[ºo]\s*(\d+),\s*de\s*(\d{4})", titulo
    )

    if match:
        prefixo, numero, ano = match.groups()
        return f"{prefixo} {numero}/{ano}"

    return titulo


prcs_map = {item["nome_norma"]: item["nomeProposicao"] for item in prcs_transf_norma}

origens = {}
x = 0
for norma in tqdm(normas):
    origem_cd_norm = None
    casas_cd = []
    if norma["titulo"].startswith("Resolução da Câmara dos Deputados"):
        origem_cd = prcs_map.get(normalizar_resolucao_cd(norma["titulo"]))
        if not origem_cd:
            x += 1
            print("Não encontrado na PRC:", norma["titulo"])
            continue
        else:
            origem_cd_norm = [origem_cd]
            casas_cd = ["CD"]

    urn = norma.get("urn")
    casa_origem = get_casa_iniciadora(urn, origens_sf_map)

    origem_lexml = norma.get("relacionamentos")

    origem_normas = None

    if origens_normas_leg_br_map.get(urn):
        origem_normas = origens_normas_leg_br_map.get(urn, {}).get("name")

    origem_sf = extract_origin_from_sf(origens_sf_map.get(urn, {}), casa_origem)

    if  not fases_tramitacao.get(urn, {}).get("tramitacao"):
        print("URN sem tramitação:", urn)

    if not origem_lexml and not origem_normas and not origem_cd_norm and not origem_sf:
        print("URN sem origens:", urn)
        x += 1
        continue
    
    origem_lexml_extraida = extract_origin_from_lexml(origem_lexml)

    origem_lexml_norm, casas_lexml = normalize_origin(
        casa_origem, origem_lexml_extraida, urn
    )

    origem_normas_leg_br_extraida = extract_origin_from_normas_leg_br(origem_normas)

    origem_normas_leg_br_norm, casas_normas_leg_br = normalize_origin(
        casa_origem, origem_normas_leg_br_extraida, urn
    )

    origem_sf_norm, casas_sf = normalize_origin_from_sf(origem_sf)
    
    origem_final, casas_final = get_final_origin(origem_sf_norm, urn)

    origens[urn] = {
        "casa_origem": casa_origem,
        "origem_lexml": origem_lexml,
        "origem_lexml_norm": origem_lexml_norm,
        "origem_normas.leg.br": origem_normas,
        "origem_normas.leg.br_norm": origem_normas_leg_br_norm,
        "origem_sf": origem_sf,
        "origem_sf_norm": origem_sf_norm,
        "origem_final": origem_final,
        "casas": casas_final,
    }

with open(
    "data/normas/metadados/proposicoes_origem_normalizadas.json", "w", encoding="utf-8"
) as f:
    json.dump(origens, f, indent=4, ensure_ascii=False)

print("Total consolidado:", len(origens))
print("Não encontrado:", x)