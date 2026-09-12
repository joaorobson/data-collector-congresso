import json
from src.models.norma import Norma, TipoNorma
from src.models.proposicao import *
from tqdm import tqdm
import re
from datetime import datetime
import pandas as pd



normas_path = "data/normas/metadados/normas.json"
proposicoes_origem = "data/normas/metadados/proposicoes_origem_normalizadas.json"
proposicoes_origem_nao_encontradas = "data/normas/metadados/proposicoes_origem_nao_encontradas.json"

proposicoes_senado_path = "data/senado/metadados/proposicoes.json"
emendas_senado_path = "data/senado/metadados/emendas.json"
relatorios_senado_path = "data/senado/metadados/relatorios_e_pareceres.json"

proposicoes_camara_path = "data/camara/metadados/proposicoes.json"
emendas_camara_path = "data/camara/metadados/emendas.json"
relatorios_camara_path = "data/camara/metadados/relatorios_e_pareceres.json"
autoria_proposicoes_camara_path = "data/camara/metadados/autoria_proposicoes.json"

with open(normas_path, "r", encoding="utf-8") as f:
    normas = json.load(f)

with open(proposicoes_senado_path, "r", encoding="utf-8") as f:
    proposicoes_senado = json.load(f)

with open(proposicoes_camara_path, "r", encoding="utf-8") as f:
    proposicoes_camara = json.load(f)

with open(emendas_senado_path, "r", encoding="utf-8") as f:
    emendas_senado = json.load(f)

with open(relatorios_senado_path, "r", encoding="utf-8") as f:
    relatorios_senado = json.load(f)

with open(emendas_camara_path, "r", encoding="utf-8") as f:
    emendas_camara = json.load(f)

with open(relatorios_camara_path, "r", encoding="utf-8") as f:
    relatorios_camara = json.load(f)

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

def normalize_emendas_cd(emendas: list, id_emenda: int, id_proposicao: int):
    emendas_norm = []
    for emenda in emendas:
        emendas_norm.append(Emenda(
            id=id_emenda,
            id_proposicao=id_proposicao,
            numero=int(emenda.get("numero")),
            id_original=int(emenda.get("id")),
            data_apresentacao=emenda.get("dataApresentacao"),
            url_doc=emenda.get("urlInteiroTeor"),
            url_metadados=emenda.get("uri")
        ))
        id_emenda += 1

    return emendas_norm, id_emenda

def normalize_relatorios_cd(relatorios: list, id_relatorio: int, id_proposicao: int):
    relatorios_norm = []
    for relatorio in relatorios:
        relatorios_norm.append(
            Relatorio(
                id=id_relatorio,
                id_proposicao=id_proposicao,
                id_original=int(relatorio.get("id")),
                data_apresentacao=relatorio.get("dataApresentacao"),
                url_doc=relatorio.get("urlInteiroTeor"),
                url_metadados=relatorio.get("uri")
            )
        )
        id_relatorio += 1

    return relatorios_norm, id_relatorio

def normalize_emendas_sf(emendas: list, id_emenda: int, id_proposicao: int):
    emendas_norm = []
    for emenda in emendas:
        emendas_norm.append(Emenda(
            id=id_emenda,
            id_proposicao=id_proposicao,
            numero=int(emenda.get("numero")),
            id_original=int(emenda.get("id")),
            data_apresentacao=emenda.get("dataApresentacao"),
            url_doc=emenda.get("urlDocumentoEmenda"),
            url_metadados=f"https://legis.senado.leg.br/dadosabertos/processo/emenda?idProcesso={emenda.get('idProcesso')}&v=1"
        ))
        id_emenda += 1

    return emendas_norm, id_emenda

def normalize_relatorios_sf(relatorios: list, id_relatorio: int, id_proposicao: int):
    relatorios_norm = []
    for relatorio in relatorios:
        relatorios_norm.append(
            Relatorio(
                id=id_relatorio,
                id_proposicao=id_proposicao,
                id_original=int(relatorio.get("id")),
                data_apresentacao=relatorio.get("dataRecebimento"),
                url_doc=relatorio.get("urlDocumento"),
                url_metadados=f"https://legis.senado.leg.br/dadosabertos/processo/emenda?idProcesso={relatorio.get('id')}&v=1"
            )
        )
        id_relatorio += 1

    return relatorios_norm, id_relatorio

normas_norm = []
id_proposicao = 1
id_emenda = 1
id_relatorio = 1
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
            raise(f"Tipo de norma inválido para a norma {urn}: {tipo_norma}")
    else:
        print(f"Tipo de norma não especificado para a norma {urn}")

    proposicoes_origem_urn = proposicoes_origem[urn]
    proposicoes_camara_urn = proposicoes_camara[urn]
    autoria_proposicoes_camara_urn = autoria_proposicoes_camara[urn]
    proposicoes_senado_urn = proposicoes_senado[urn]
    proposicoes_norm = []

    # print(urn)
    for ix, casa in enumerate(proposicoes_origem_urn["casas"]):           
        if casa == "CD":
            if urn in MISSING_PROPS and ix == MISSING_PROPS[urn]["indice"] and MISSING_PROPS[urn]["casa"] == "CD":
                print(f"Proposição faltando para a norma {urn} na posição {ix}. Pulando...")
                origem = proposicoes_camara_urn[ix].get("origem")
                ano = proposicoes_camara_urn[ix].get("ano")
                proposicoes_norm.append(Proposicao(id=id_proposicao,
                                                   urn_norma=urn,
                                                    nome=origem,
                                                    tipo=TIPOS_PROPOSICAO.get(origem.split()[0]) if origem else None,
                                                    ano=int(ano) if ano else None,
                                                    casa_atual=Casa.CAMARA,
                                                    casa_origem=get_casa(proposicoes_origem_urn["casas"][ix-1]) if ix > 0 else get_casa("CD")))
                id_proposicao += 1
                continue
            prop_cd = proposicoes_camara_urn[ix]["resultado"]["dados"][0]
            emendas = emendas_camara.get(str(prop_cd.get("id")), {}).get("resultado", [])
            emendas_norm, id_emenda = normalize_emendas_cd(emendas, id_emenda, id_proposicao)
            relatorios = relatorios_camara.get(str(prop_cd.get("id")), {}).get("resultado", [])
            relatorios_norm, id_relatorio = normalize_relatorios_cd(relatorios, id_relatorio, id_proposicao)

            autoria_prop_cd = autoria_proposicoes_camara_urn[ix]["resultado"]["dados"]
            autoria_norm = normalize_autoria(autoria_prop_cd, casa)
            proposicoes_norm.append(Proposicao(id=id_proposicao,
                                               id_original=prop_cd.get("id"), 
                                               urn_norma=urn,
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
                                               casa_origem=get_casa(proposicoes_origem_urn["casas"][ix-1]) if ix > 0 else get_casa("CD"),
                                               emendas=emendas_norm,
                                               relatorios=relatorios_norm))
            id_proposicao += 1
            #print(proposicoes_norm)
        elif casa == "SF":
            if urn in MISSING_PROPS and ix == MISSING_PROPS[urn]["indice"] and MISSING_PROPS[urn]["casa"] == "SF":
                print(f"Proposição faltando para a norma {urn} na posição {ix}. Pulando...")
                origem = proposicoes_senado_urn[ix].get("origem")
                ano = proposicoes_senado_urn[ix].get("ano")

                proposicoes_norm.append(Proposicao(id=id_proposicao,
                                                   nome=origem,
                                                   urn_norma=urn,
                                                   tipo=TIPOS_PROPOSICAO.get(origem.split()[0]) if origem else None,
                                                   ano=int(ano) if ano else None,
                                                   casa_atual=Casa.SENADO,
                                                   casa_origem=get_casa(proposicoes_origem_urn["casas"][ix-1]) if ix > 0 else get_casa("SF")))
                id_proposicao += 1
                continue
            prop_sf = proposicoes_senado_urn[ix]["resultado"]["dados"][0]
            emendas = emendas_senado.get(str(prop_sf.get("id")), {}).get("resultado", [])
            emendas_norm, id_emenda = normalize_emendas_sf(emendas, id_emenda, id_proposicao)
            relatorios = relatorios_senado.get(str(prop_sf.get("id")), {}).get("resultado", [])
            relatorios_norm, id_relatorio = normalize_relatorios_sf(relatorios, id_relatorio, id_proposicao)

            autoria_prop_sf = prop_sf.get("documento", {}).get("autoria", [])
            autoria_norm = normalize_autoria(autoria_prop_sf, casa)
            proposicoes_norm.append(Proposicao(id=id_proposicao,
                                               urn_norma=urn,
                                               id_original=prop_sf.get("id"), 
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
                                               casa_origem=get_casa(proposicoes_origem_urn["casas"][ix-1]) if ix > 0 else get_casa("SF"),
                                               emendas=emendas_norm,
                                               relatorios=relatorios_norm))
            id_proposicao += 1
    
    #print(proposicoes_norm)
    norma = Norma(nome=nome, urn=urn, tipo_norma=tipo_norma_enum, data_publicacao=data_publicacao, proposicoes=proposicoes_norm)
    normas_norm.append(norma)

# Conversão para df/parquet
normas_rows = []
proposicoes_rows = []
emendas_rows = []
relatorios_rows = []

for norma in normas_norm:
    normas_rows.append(
        norma.model_dump(
            mode="json",
            exclude={"proposicoes"}
        )
    )

    for proposicao in norma.proposicoes or []:
        proposicoes_rows.append(
            proposicao.model_dump(
                mode="json",
                exclude={"emendas", "relatorios"}
            )
        )

        emendas_rows.extend(
            emenda.model_dump(mode="json")
            for emenda in proposicao.emendas or []
        )

        relatorios_rows.extend(
            relatorio.model_dump(mode="json")
            for relatorio in proposicao.relatorios or []
        )

normas_df = pd.DataFrame(normas_rows)
proposicoes_df = pd.DataFrame(proposicoes_rows)
emendas_df = pd.DataFrame(emendas_rows)
relatorios_df = pd.DataFrame(relatorios_rows)

normas_df.to_parquet("data/datasets/normas.parquet", index=False)
proposicoes_df.to_parquet("data/datasets/proposicoes.parquet", index=False)
emendas_df.to_parquet("data/datasets/emendas.parquet", index=False)
relatorios_df.to_parquet("data/datasets/relatorios.parquet", index=False)