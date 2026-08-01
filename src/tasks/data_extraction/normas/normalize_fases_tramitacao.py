import json
from tqdm import tqdm
import re

with open(
    "data/normas/metadados/fases_tramitacao.json",
    "r",
    encoding="utf-8",
) as f:
    fases_tramitacao = json.load(f)

fases_norm = {}
CASA_PARA_SIGLA = {"CAMARA": "CD", "SENADO": "SF", "CONGRESSO": "CN", "PRESIDENCIA": "PR"}

def normalizar_proposicao(proposicao):
    """
    Normaliza a identificação da proposição.

    Exemplos:
        "PL  2303/2015"
        -> "PL 2303/2015"

        "PL 4401/2021 (Nº Anterior: PL 2303/2015)"
        -> "PL 4401/2021"

        "PL 2.303/2015"
        -> "PL 2303/2015"
    """
    if proposicao is None:
        return None

    if not isinstance(proposicao, str):
        return proposicao

    # Remove pontos usados como separadores de milhar.
    proposicao = re.sub(
        r"(?<=\d)\.(?=\d)",
        "",
        proposicao
    )

    # Remove o conteúdo entre parênteses.
    proposicao = re.sub(
        r"\s*\([^)]*\)",
        "",
        proposicao
    )

    # Substitui múltiplos espaços por apenas um.
    proposicao = re.sub(
        r"\s+",
        " ",
        proposicao
    )

    return proposicao.strip().upper()

for urn, fases in tqdm(fases_tramitacao.items()):
    if (urn.startswith("urn:lex:br:federal:medida.provisoria") or  
        urn.startswith("urn:lex:br:senado.federal:resolucao") or 
        urn.startswith("urn:lex:br:camara.deputados:resolucao") or
        urn.startswith("urn:lex:br:congresso.nacional:resolucao") or
        fases.get("proposicao_origem").get("proposicao").split()[0] in ["MPV", "PLN", "PLV", "PDN", "PDR"]):
        proposicao = re.sub(r"(?<=\d)\.(?=\d)", "", fases.get("proposicao_origem").get("proposicao"))
        fases_norm[urn] = {
            "tramitacao": [proposicao],
            "casas": [fases.get("proposicao_origem").get("casa")]
        }
    elif not fases.get("ignorado"):
        if type(fases.get("resultado")) is dict:
            casas = []
            tramitacao = []
            for fase in fases.get("resultado").get("fases"):
                proposicao = fase.get("identificacaoMateria")
                if proposicao:
                    proposicao = normalizar_proposicao(proposicao)
                casas.append(CASA_PARA_SIGLA.get(fase.get("casa")))
                tramitacao.append(proposicao)
            fases_norm[urn] = {
                "tramitacao": tramitacao,
                "casas": casas
            }
        else:
            print(urn)
            print(fases.get("proposicao_origem").get("proposicao"))
    else:
        print(urn)

with open(
    "data/normas/metadados/fases_tramitacao_norm.json", "w", encoding="utf-8"
) as f:
    json.dump(fases_norm, f, indent=4, ensure_ascii=False)