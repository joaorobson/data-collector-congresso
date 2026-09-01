import json
import re
from tqdm import tqdm

with open(
    "data/normas/metadados/fases_tramitacao.json",
    "r",
    encoding="utf-8",
) as f:
    fases_tramitacao = json.load(f)

fases_norm = {}
CASA_PARA_SIGLA = {
    "CAMARA": "CD",
    "SENADO": "SF",
    "CONGRESSO": "CN",
    "PRESIDENCIA": "PR",
}


def normalizar_proposicao(proposicao):
    """Normaliza a identificação da proposição.

    Exemplos:
        "PL  2303/2015" -> "PL 2303/2015"
        "PL 4401/2021 (Nº Anterior: PL 2303/2015)" -> "PL 4401/2021"
        "PL 2.303/2015" -> "PL 2303/2015"
    """
    if proposicao is None or not isinstance(proposicao, str):
        return proposicao

    # Remove pontos usados como separadores de milhar
    proposicao = re.sub(r"(?<=\d)\.(?=\d)", "", proposicao)

    # Remove o conteúdo entre parênteses
    proposicao = re.sub(r"\s*\([^)]*\)", "", proposicao)

    # Substitui múltiplos espaços por apenas um
    proposicao = re.sub(r"\s+", " ", proposicao)

    return proposicao.strip().upper()


for urn, fases in tqdm(fases_tramitacao.items()):
    proposicao_origem_dict = fases.get("proposicao_origem") or {}
    proposicao_origem = proposicao_origem_dict.get("proposicao", "")
    sigla_origem = proposicao_origem.split()[0] if proposicao_origem else ""

    if (
        urn.startswith("urn:lex:br:federal:medida.provisoria")
        or urn.startswith("urn:lex:br:senado.federal:resolucao")
        or urn.startswith("urn:lex:br:camara.deputados:resolucao")
        or urn.startswith("urn:lex:br:congresso.nacional:resolucao")
        or sigla_origem in ["MPV", "PLN", "PLV", "PDN", "PDR"]
    ):
        proposicao = re.sub(r"(?<=\d)\.(?=\d)", "", proposicao_origem)
        fases_norm[urn] = {
            "tramitacao": [proposicao],
            "casas": [proposicao_origem_dict.get("casa")],
            "tem_veto": False,
        }

    elif not fases.get("ignorado"):
        resultado = fases.get("resultado")
        if isinstance(resultado, dict):
            casas = []
            tramitacao = []
            fases_lista = resultado.get("fases") or []

            for fase in fases_lista:
                if not isinstance(fase, dict):
                    continue
                casa_sigla = CASA_PARA_SIGLA.get(fase.get("casa"))

                if casa_sigla == "PR":
                    continue
                
                prop = fase.get("identificacaoMateria")
                if prop:
                    prop = normalizar_proposicao(prop)
                casas.append(casa_sigla)
                tramitacao.append(prop)

            # Captura a flag de veto do resultado
            tem_veto = bool(resultado.get("temVeto"))

            fases_norm[urn] = {
                "tramitacao": tramitacao,
                "casas": casas,
                "tem_veto": tem_veto,
            }
        else:
            print("Resultado inválido:", urn)
            print("Origem:", proposicao_origem)
    else:
        print("Ignorado:", urn)

with open(
    "data/normas/metadados/fases_tramitacao_norm.json", "w", encoding="utf-8"
) as f:
    json.dump(fases_norm, f, indent=4, ensure_ascii=False)