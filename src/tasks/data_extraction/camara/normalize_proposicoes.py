import ijson
import json
import re
from datetime import datetime
from tqdm import tqdm

def parse_datetime(valor):
    if not valor:
        return None

    try:
        return datetime.fromisoformat(valor)
    except:
        return None

def get_cargo_tipo(autor: dict):
    if autor['tipo'] in ('Deputado(a)', 'MISTA CPI', 'Plenário Virtual CN', 'COMISSÃO ESPECIAL') or autor['nome'] in ('Câmara dos Deputados', 'Poder Executivo'):
        return "CD"
    elif "Senado Federal" in autor['nome']:
        return "SF"


def get_casa_origem(data: dict, autores) -> str:
    sigla = data.get("siglaTipo")
    if sigla == "PRF":
        return "SF"
    cargos = set([get_cargo_tipo(autor) for autor in autores])
    
    if cargos == {"CD"}:
        return "CD"
    elif cargos == {"SF"}:
        return "SF"
    return "CD"

def extrair_norma_gerada(descricao_situacao: str, situacao: str):
    if not descricao_situacao and not situacao:
        return None

    descricao = (descricao_situacao or "").lower()
    situacao = (situacao or "").strip()

    # 🔹 1. Gate EXATO (evita falso positivo)
    if "transformado em norma jurídica" not in descricao:
        return None

    # 🔹 2. Remove prefixo (ex: "MESA - ")
    situacao_limpa = re.sub(r"^[A-Z0-9\(\)\/]+?\s*-\s*", "", situacao)

    # 🔹 3. Regex baseada nos tipos reais
    pattern = re.compile(
        r'(?i)('
        r'decreto legislativo|'
        r'emenda constitucional|'
        r'lei complementar|'
        r'lei ordinária|'
        r'resolução da câmara dos deputados|'
        r'resolução do congresso nacional'
        r')[^\d]*(\d+)[/](\d{2,4})'
    )

    match = pattern.search(situacao_limpa)

    if not match:
        return {
            "nome": None,
            "ano": None,
            "ementa": None,
            "data_publicacao": None
        }

    tipo, numero, ano = match.groups()

    # 🔹 4. Normalização do tipo
    tipo = tipo.lower()

    mapping = {
        "decreto legislativo": "Decreto Legislativo",
        "emenda constitucional": "Emenda Constitucional",
        "lei complementar": "Lei Complementar",
        "lei ordinária": "Lei Ordinária",
        "resolução da câmara dos deputados": "Resolução da Câmara dos Deputados",
        "resolução do congresso nacional": "Resolução do Congresso Nacional",
    }

    tipo = mapping.get(tipo, tipo.title())

    # 🔹 5. Ano
    ano = int(ano)
    if ano < 100:
        ano += 2000

    nome = f"{tipo} nº {numero}/{ano}"

    return {
        "nome": nome,
        "ano": ano,
        "ementa": None,
        "data_publicacao": None
    }

with open("data/camara/situacao_e_nome_origem_proposicoes.json", "r", encoding="utf-8") as f:
    situacao_e_nome_origem_dict = json.load(f)



materias_normalizadas = []

with open(
    "data/camara/proposicoes_com_autoria.json",
    "r",
    encoding="utf-8"
) as f:
    objects = ijson.items(f, 'item')
    for i, d in enumerate(tqdm(objects, desc="Processando proposições", unit=" proposições")):

        # =========================
        # EMENTA
        # =========================
        ementa = (
            d.get("ementa", "") or ""
        ).strip()

        # =========================
        # DATA APRESENTAÇÃO
        # =========================
        data_apresentacao = parse_datetime(
            d.get("dataApresentacao")
        )

        # =========================
        # PALAVRAS CHAVE
        # =========================
        keywords = d.get("keywords", "") or ""

        palavras_chave = [
            p.strip()
            for p in keywords.split(",")
            if p.strip()
        ]

        # =========================
        # AUTORIA
        # =========================
        autores = []

        for autor in d.get("autoria", []):

            autores.append({
                "nome": autor.get("nome"),
                "tipo": autor.get("tipo"),
                "uf": None,
                "sexo": None
            })

        # =========================
        # SITUAÇÃO
        # =========================
        status = d.get("statusProposicao", {})

        situacao_atual = status.get(
            "descricaoSituacao"
        ) or situacao_e_nome_origem_dict.get(str(d.get("id")), {}).get("situacao")

        # =========================
        # TRAMITAÇÃO
        # =========================
        em_tramitacao = (
            situacao_atual != "Arquivada"
            and situacao_atual != "Transformado em Norma Jurídica"
        )

        # =========================
        # NORMA GERADA
        # =========================
        norma_gerada = extrair_norma_gerada(status.get("descricaoSituacao"), situacao_e_nome_origem_dict.get(str(d.get("id")), {}).get("situacao"))

        transformado_em_norma = (
            norma_gerada is not None
        )

        # =========================
        # OBJETO FINAL
        # =========================
        materia = {
            "id": d.get("id"),
            "uri": d.get("uri"),
            "ano": d.get("ano"),
            "nome": (
                f"{d.get('siglaTipo')} "
                f"{d.get('numero')}/"
                f"{d.get('ano')}"
            ),
            "nome_inicial": situacao_e_nome_origem_dict.get(str(d.get("id")), {}).get("nome_origem"),
            "numero": d.get("numero"),
            "ementa": ementa,
            "data_apresentacao": data_apresentacao,
            "palavras_chave": palavras_chave,
            "autoria": autores,
            "situacao_atual": situacao_atual,
            "em_tramitacao": em_tramitacao,
            "casa_atual": "CD",
            "casa_origem": get_casa_origem(d, autores),
            "transformado_em_norma": transformado_em_norma,
            "norma_gerada": norma_gerada,

            # auxiliares para conversão posterior
            "sigla_tipo": d.get("siglaTipo"),
            "tipo": d.get("descricaoTipo")
        }

        materias_normalizadas.append(materia)



with open(
    "data/camara/proposicoes_normalizadas.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        materias_normalizadas,
        f,
        ensure_ascii=False,
        indent=2,
        default=str
    )