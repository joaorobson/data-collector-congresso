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


def extrair_norma_gerada(status):

    if not status:
        return None

    descricao = (
        status.get("descricaoSituacao", "") or ""
    ).lower()

    if "transformado em norma jurídica" not in descricao:
        return None

    despacho = status.get("despacho", "")

    padrao = re.search(
        r"(DECRETO LEGISLATIVO|LEI|EMENDA CONSTITUCIONAL)\s+(\d+)\/(\d+)",
        despacho,
        re.IGNORECASE
    )

    if not padrao:
        return {
            "nome": None,
            "ano": None,
            "ementa": None,
            "data_publicacao": parse_datetime(
                status.get("dataHora")
            )
        }

    tipo_norma = padrao.group(1).title()
    numero = padrao.group(2)
    ano = padrao.group(3)

    if len(ano) == 2:
        ano = int(f"20{ano}")
    else:
        ano = int(ano)

    return {
        "nome": f"{tipo_norma} nº {numero}/{ano}",
        "ano": ano,
        "ementa": None,
        "data_publicacao": parse_datetime(
            status.get("dataHora")
        )
    }

with open("data/camara/nome_origem_proposicoes.json", "r", encoding="utf-8") as f:
    nome_origem_dict = json.load(f)



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
        )

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
        norma_gerada = extrair_norma_gerada(status)

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
            "nome_inicial": nome_origem_dict.get(str(d.get("id"))),
            "numero": d.get("numero"),
            "ementa": ementa,
            "data_apresentacao": data_apresentacao,
            "palavras_chave": palavras_chave,
            "autoria": autores,
            "situacao_atual": situacao_atual,
            "em_tramitacao": em_tramitacao,
            "casa_atual": "CD",
            "casa_origem": "CD",
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