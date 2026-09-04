import json
from src.models.norma import Norma, TipoNorma
from src.models.proposicao import *
from tqdm import tqdm
import re
from datetime import datetime

normas_path = "data/normas/metadados/normas.json"
proposicoes_origem = "data/normas/metadados/proposicoes_origem_normalizadas.json"
proposicoes_origem_nao_encontradas = "data/normas/metadados/proposicoes_origem_nao_encontradas.json"
proposicoes_senado_path = "data/senado/metadados/proposicoes.json"
proposicoes_camara_path = "data/camara/metadados/proposicoes.json"
autoria_proposicoes_camara_path = "data/camara/metadados/autoria_proposicoes.json"
emendas_path = "data/senado/metadados/emendas.json"

with open(normas_path, "r", encoding="utf-8") as f:
    normas = json.load(f)

with open(proposicoes_senado_path, "r", encoding="utf-8") as f:
    proposicoes_senado = json.load(f)

with open(proposicoes_camara_path, "r", encoding="utf-8") as f:
    proposicoes_camara = json.load(f)

with open(emendas_path, "r", encoding="utf-8") as f:
    emendas = json.load(f)

with open(proposicoes_origem, "r", encoding="utf-8") as f:
    proposicoes_origem = json.load(f)

with open(proposicoes_origem_nao_encontradas, "r", encoding="utf-8") as f:
    proposicoes_origem_nao_encontradas = json.load(f)

with open(autoria_proposicoes_camara_path, "r", encoding="utf-8") as f:
    autoria_proposicoes_camara = json.load(f)

TIPOS_COMISSAO_CD = {
    "COMISSÃO DIRETORA",
    "COMISSÃO ESPECIAL",
    "COMISSÃO MISTA PERMANENTE",
    "COMISSÃO PARLAMENTAR DE INQUÉRITO",
    "COMISSÃO PERMANENTE",
    "MISTA CPI",
    "PERMANENTE DO SENADO FEDERAL",
}

TIPOS_COMISSAO_SF = {
    "COMISSAO",
    "COMISSAO_CAMARA",
    "COMISSAO_CONGRESSO",
    "COMISSAO_SENADO",
    "COMISSAO_SENADO_CAMARA",
    "CMO",
}

TIPOS_ORGAO_SF = {
    "SENADO",
    "CAMARA",
    "MESAS_SF_CD",
}

TIPOS_PROPOSICAO = {
    "PEC": TipoProposicao.PEC,
    "PL": TipoProposicao.PL,
    "PLC": TipoProposicao.PL,
    "PLS": TipoProposicao.PL,
    "PLP": TipoProposicao.PLP,
    "PDG": TipoProposicao.PDG,
    "PR": TipoProposicao.PR,
    "PRS": TipoProposicao.PR,
    "PRC": TipoProposicao.PR,
    "PDL": TipoProposicao.PDL,
    "PDC": TipoProposicao.PDL,
    "PDS": TipoProposicao.PDL,
    "PLV": TipoProposicao.MPV,
    "MPV": TipoProposicao.MPV,
    "SDS": TipoProposicao.EMENDA,
    "SCD": TipoProposicao.EMENDA,
    "ECD": TipoProposicao.EMENDA,
    "DEN": TipoProposicao.DENUNCIA,
}

MISSING_PROPS = {
    "urn:lex:br:federal:decreto.legislativo:2010-07-21;556": {"casa": "CD", "indice": 0},
    "urn:lex:br:federal:decreto.legislativo:2011-05-26;136": {"casa": "CD", "indice": 1},
    "urn:lex:br:federal:decreto.legislativo:2013-09-26;382": {"casa": "CD", "indice": 0},
    "urn:lex:br:federal:decreto.legislativo:2013-11-28;402": {"casa": "CD", "indice": 0},
    "urn:lex:br:federal:decreto.legislativo:2013-09-26;381": {"casa": "CD", "indice": 0},
}

def _normalize_autor_cd(autor: dict) -> Autor:
    tipo = autor["tipo"].strip().upper()
    nome = autor["nome"].strip()

    if tipo.startswith("DEPUTADO"):
        return Parlamentar(
            tipo=TipoAutor.PARLAMENTAR,
            nome=nome,
            cargo=CargoParlamentar.DEPUTADO,
        )

    if tipo.startswith("SENADOR"):
        return Parlamentar(
            tipo=TipoAutor.PARLAMENTAR,
            nome=nome,
            cargo=CargoParlamentar.SENADOR,
        )

    if tipo in TIPOS_COMISSAO_CD:
        return Orgao(
            tipo=TipoAutor.ORGAO,
            nome=nome,
            subtipo=TipoOrgao.COMISSAO,
        )

    if tipo == "CONSELHO":
        return Orgao(
            tipo=TipoAutor.ORGAO,
            nome=nome,
            subtipo=TipoOrgao.CONSELHO,
        )

    return Orgao(
        tipo=TipoAutor.ORGAO,
        nome=nome,
        subtipo=TipoOrgao.ORGAO,
    )

def _normalize_autor_sf(autor: dict) -> Autor | None:
    print(autor)
    tipo = autor.get("siglaTipo", "").strip().upper()
    nome = autor.get("autor", "").strip()

    if not nome:
        return None

    if tipo == "CIDADAO":
        return Cidadao(
            tipo=TipoAutor.CIDADAO,
            nome=nome,
        )

    if tipo == "PRESIDENTE_REPUBLICA":
        return Entidade(
            tipo=TipoAutor.ENTIDADE,
            nome=nome,
            subtipo=TipoEntidade.PODER_EXECUTIVO,
        )

    if tipo == "LIDER" or tipo == "SENADOR":
        return Parlamentar(
                tipo=TipoAutor.PARLAMENTAR,
                nome=nome,
                cargo=CargoParlamentar.SENADOR,
                uf=autor.get("uf"),
                partido=autor.get("siglaPartido"),
        )

    if tipo == "DEPUTADO":
        return Parlamentar(
            tipo=TipoAutor.PARLAMENTAR,
            nome=nome,
            cargo=CargoParlamentar.DEPUTADO,
            uf=autor.get("uf"),
            partido=autor.get("siglaPartido"),
        )
    
    if tipo == "PARLAMENTAR":
        cargo = autor.get("siglaCargo", "").strip().upper()

        if cargo == "SENADOR":
            cargo_norm = CargoParlamentar.SENADOR
        elif cargo == "DEPUTADO":
            cargo_norm = CargoParlamentar.DEPUTADO
        else:
            return None

        return Parlamentar(
            tipo=TipoAutor.PARLAMENTAR,
            nome=nome,
            cargo=cargo_norm,
            uf=autor.get("uf"),
            partido=autor.get("siglaPartido"),
        )

    if tipo in TIPOS_COMISSAO_SF:
        return Orgao(
            tipo=TipoAutor.ORGAO,
            nome=nome,
            subtipo=TipoOrgao.COMISSAO,
        )

    if tipo == "SENADO":
        return Orgao(
            tipo=TipoAutor.ORGAO,
            nome=nome,
            subtipo=TipoOrgao.SENADO,
        )

    if tipo == "CAMARA":
        return Orgao(
            tipo=TipoAutor.ORGAO,
            nome=nome,
            subtipo=TipoOrgao.CAMARA,
        )

    if tipo == "MESAS_SF_CD":
        return Orgao(
            tipo=TipoAutor.ORGAO,
            nome=nome,
            subtipo=TipoOrgao.MESA,
        )

    if tipo == "ENTE_JURIDICO":
        return Entidade(
            tipo=TipoAutor.ENTIDADE,
            nome=nome,
            subtipo=TipoEntidade.PODER_LEGISLATIVO,
        )

    return None

def normalize_autoria(autoria: list[dict], casa: str) -> list[Autor]:
    if casa == "CD":
        return [_normalize_autor_cd(autor) for autor in autoria]

    if casa == "SF":
        return [_normalize_autor_sf(autor) for autor in autoria]

    raise ValueError(f"Casa inválida: {casa}")

def get_casa(casa):
    if casa == "CD":
        return Casa.CAMARA
    elif casa == "SF":
        return Casa.SENADO
    elif casa == "CN":
        return Casa.CONGRESSO

for norma in tqdm(normas):
    urn = norma.get("urn")
    if urn in proposicoes_origem_nao_encontradas:
        continue
    tipo_norma = norma.get("tipo")
    nome = norma.get("titulo")
    match = re.search(r":(\d{4}-\d{2}-\d{2})(?:;|\b)", urn)
    data_publicacao = None
    if match:
        data_publicacao = datetime.strptime(match.group(1), "%Y-%m-%d")
    
    if tipo_norma:
        try:
            tipo_norma_enum = TipoNorma(tipo_norma)
        except ValueError:
            print(f"Tipo de norma inválido para a norma {urn}: {tipo_norma}")
    else:
        print(f"Tipo de norma não especificado para a norma {urn}")

    proposicoes_origem_urn = proposicoes_origem[urn]
    proposicoes_camara_urn = proposicoes_camara[urn]
    autoria_proposicoes_camara_urn = autoria_proposicoes_camara[urn]
    proposicoes_senado_urn = proposicoes_senado[urn]
    proposicoes_norm = []
    print(urn)
    for ix, casa in enumerate(proposicoes_origem_urn["casas"]):           
        if casa == "CD":
            if urn in MISSING_PROPS and ix == MISSING_PROPS[urn]["indice"] and MISSING_PROPS[urn]["casa"] == "CD":
                print(f"Proposição faltando para a norma {urn} na posição {ix}. Pulando...")
                proposicoes_norm.append(None)
                continue
            prop_cd = proposicoes_camara_urn[ix]["resultado"]["dados"][0]
            autoria_prop_cd = autoria_proposicoes_camara_urn[ix]["resultado"]["dados"]
            autoria_norm = normalize_autoria(autoria_prop_cd, casa)
            proposicoes_norm.append(Proposicao(id_original=prop_cd.get("id"), 
                                               nome=f"{prop_cd.get('siglaTipo')} {prop_cd.get('numero')}/{prop_cd.get('ano')}",
                                               ano=prop_cd.get("ano"), 
                                               numero=prop_cd.get("numero"),
                                               tipo=TIPOS_PROPOSICAO.get(prop_cd.get("siglaTipo")),
                                               autoria=autoria_norm,
                                               ementa=prop_cd.get("ementa"), 
                                               data_apresentacao=prop_cd.get("dataApresentacao"),
                                               url_doc=prop_cd.get("urlInteiroTeor"),
                                               url_metadados=prop_cd.get("uri"),
                                               casa_atual=Casa.CAMARA,
                                               casa_origem=get_casa(proposicoes_origem_urn["casas"][ix-1]) if ix > 0 else get_casa("CD")))
            #print(proposicoes_norm)
        elif casa == "SF":
            if urn in MISSING_PROPS and ix == MISSING_PROPS[urn]["indice"] and MISSING_PROPS[urn]["casa"] == "SF":
                print(f"Proposição faltando para a norma {urn} na posição {ix}. Pulando...")
                proposicoes_norm.append(None)
                continue
            prop_sf = proposicoes_senado_urn[ix]["resultado"]["dados"][0]

            autoria_prop_sf = prop_sf.get("documento", {}).get("autoria", [])
            autoria_norm = normalize_autoria(autoria_prop_sf, casa)
            proposicoes_norm.append(Proposicao(id_original=prop_sf.get("id"), 
                                               nome=prop_sf.get("identificacao"),
                                               ano=prop_sf.get("ano"), 
                                               numero=prop_sf.get("numero"), 
                                               tipo=TIPOS_PROPOSICAO.get(prop_sf.get("sigla")),
                                               autoria=autoria_norm, 
                                               ementa=prop_sf.get("conteudo", {}).get("ementa"), 
                                               data_apresentacao=prop_sf.get("documento", {}).get("dataApresentacao"),
                                               url_doc=prop_sf.get("documento", {}).get("url"),
                                               url_metadados=f"https://legis.senado.leg.br/dadosabertos/processo/{prop_sf.get('id')}",
                                               casa_atual=Casa.SENADO,
                                               casa_origem=get_casa(proposicoes_origem_urn["casas"][ix-1]) if ix > 0 else get_casa("SF")))
        #print('--------', proposicoes_norm)
    


    norma = Norma(nome=nome, urn=urn, tipo_norma=tipo_norma_enum, data_publicacao=data_publicacao, proposicoes=[])



print(norma)


"""for urn, props in proposicoes.items():
    if len(props) > 1:
        print(props)    
     for resultado in prop.get("resultado", []):
        id_prop = str(resultado.get("id"))
        emendas_prop = emendas.get(str(id_prop), {}).get("resultado", [])
        print(emendas_prop)
        break
    break """ 