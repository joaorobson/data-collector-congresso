import json
from src.models.proposicao import Autor, Casa, Tipo, Proposicao, Materia, Norma, Emenda, Relatorio
import pandas as pd
from datetime import datetime
from typing import Dict, Any
from tqdm import tqdm
import unicodedata
from difflib import SequenceMatcher
import re

from rapidfuzz import fuzz

def parse_datetime(dt: str) -> datetime:
    if not dt:
        return None
    dt = dt.replace("T", " ").replace("Z", "")
    return datetime.fromisoformat(dt)

def parse_casa(casa: str) -> str:
    if casa == "CD":
        return "Câmara dos Deputados"
    elif casa == "SF":
        return "Senado Federal"
    elif casa == "CN":
        return "Congresso Nacional"
    else:
        return casa
    
def parse_tipo(tipo: str) -> str:
    if tipo.startswith("Projeto de Resolução"):
        return "Projeto de Resolução"
    return tipo
    
def parse_sigla_tipo(sigla: str) -> str:
    if sigla in ["PRC", "PRS", "PRF", "PRN"]:
        return "PR"
    return sigla

def json_to_proposicao(data: Dict[str, Any]) -> Proposicao:
    return Proposicao(
        id=data["id"],
        uri=data["uri"],
        ano=data["ano"],
        nome=data["nome"],
        nome_inicial=data.get("nome_inicial"),
        numero=str(data.get("numero")),

        ementa=data.get("ementa", ""),
        palavras_chave=data.get("palavras_chave", []),

        tipo=parse_tipo(data.get("tipo")),
        sigla_tipo=parse_sigla_tipo(data.get("sigla_tipo")),

        autoria=[
            Autor(
                nome=a.get("nome"),
                tipo=a.get("tipo"),
                uf=a.get("uf"),
                sexo=a.get("sexo"),
            )
            for a in data.get("autoria", [])
        ],

        situacao_atual=data.get("situacao_atual"),
        em_tramitacao=data.get("em_tramitacao", False),

        data_apresentacao=parse_datetime(data.get("data_apresentacao")),

        casa_atual=parse_casa(data.get("casa_atual")),
        casa_origem=parse_casa(data.get("casa_origem")),


        transformado_em_norma=data.get("transformado_em_norma", False),

        norma_gerada=Norma(
            nome=data["norma_gerada"]["nome"],
            ano=data["norma_gerada"]["ano"],
            ementa=data["norma_gerada"].get("ementa"),
            data_publicacao=parse_datetime(
                data["norma_gerada"].get("data_publicacao")
            ),
        ) if data.get("norma_gerada") else None,
    )


def json_to_materia(p: Proposicao, data: Dict[str, Any]) -> Materia:
    return Materia(
        id=0,
        casa_iniciadora=p.casa_origem,
        tipo=p.tipo,
        sigla_tipo=p.sigla_tipo,
        proposicao_sf=p if p.casa_origem == Casa.SENADO else None,
        proposicao_cd=p if p.casa_origem == Casa.CAMARA else None,
        transformada_em_norma=data.get("transformado_em_norma", False),
        norma_gerada=Norma(
            nome=data["norma_gerada"]["nome"],
            ano=data["norma_gerada"]["ano"],
            ementa=data["norma_gerada"].get("ementa"),
            data_publicacao=parse_datetime(
                data["norma_gerada"].get("data_publicacao")
            ),
        ) if data.get("norma_gerada") else None,
    )

def normalizar(texto):
    if pd.isna(texto):
        return None
    
    texto = texto.lower()
    
    # remove acentos
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    
    # remove (2ª autuação) etc
    texto = re.sub(r"\(.*?\)", "", texto)
    
    # remove pontuação
    texto = re.sub(r"[^\w\s]", "", texto)
    
    # normaliza espaços
    texto = re.sub(r"\s+", " ", texto)
    
    return texto.strip()


def similar(a, b):
    if pd.isna(a) or pd.isna(b):
        return 0
    
    return SequenceMatcher(None, str(a), str(b)).ratio()

def similarity_match(row):
    return (
        row['sim'] > 0.9 or
        row['sim_partial'] > 0.9 or
        row['sim_token'] > 0.85
    )


def merge_prns(prns_cd, prns_sf):
    merged = []
    for prn_cd in prns_cd:
        melhor_match = None
        melhor_score = 0.0
        
        for prn_sf in prns_sf:
            score = similar(prn_cd.nome, prn_sf.nome)
            if score > melhor_score:
                melhor_score = score
                melhor_match = prn_sf
        
        if melhor_score > 0.8:  # threshold de similaridade
            merged.append((prn_cd, melhor_match, melhor_score))
    
    return merged


with open("data/senado/proposicoes_normalizadas.json", "r", encoding="utf-8") as f:
    proposicoes_sf = json.load(f)

with open("data/camara/proposicoes_normalizadas.json", "r", encoding="utf-8") as f:
    proposicoes_cd = json.load(f)

prn_cd_por_nome = {p["nome"]: p for p in proposicoes_cd if p["sigla_tipo"] == "PRN"}
prn_sf_por_nome = {p["nome"]: p for p in proposicoes_sf if p["sigla_tipo"] == "PRN"}

props_cd = pd.read_json("data/camara/proposicoes_normalizadas.json", encoding="utf-8")
props_sf = pd.read_json("data/senado/proposicoes_normalizadas.json", encoding="utf-8")


# Merge PRNs

resolucoes_cn_cd = props_cd[props_cd.sigla_tipo.isin(["PRN"])].copy().reset_index(drop=True)
resolucoes_cn_sf = props_sf[props_sf.sigla_tipo.isin(["PRN"])].copy().reset_index(drop=True)

prns_merge = resolucoes_cn_cd.merge(resolucoes_cn_sf,
    on='nome',
    how='inner',
    suffixes=('_df1', '_df2')
)


prns_merge['e1'] = prns_merge['ementa_df1'].apply(normalizar)
prns_merge['e2'] = prns_merge['ementa_df2'].apply(normalizar)

# -------------------------
# Similaridades (rápido)
# -------------------------
prns_merge['sim'] = [
    similar(a, b) for a, b in zip(prns_merge['e1'], prns_merge['e2'])
]

prns_merge['sim_partial'] = [
    fuzz.partial_ratio(a, b) for a, b in zip(prns_merge['e1'], prns_merge['e2'])
]

prns_merge['sim_token'] = [
    fuzz.token_set_ratio(a, b) for a, b in zip(prns_merge['e1'], prns_merge['e2'])
]

# -------------------------
# Match inteligente
# -------------------------
prns_merge['match'] = prns_merge.apply(similarity_match, axis=1)

# -------------------------
# 🎯 INTERSEÇÃO FINAL
# -------------------------
nomes_intersecao = prns_merge.loc[prns_merge['match'], 'nome'].tolist()

print("Total na interseção inteligente:", len(nomes_intersecao), nomes_intersecao)

materias = []

nomes_cd = set(resolucoes_cn_cd["nome"])
nomes_sf = set(resolucoes_cn_sf["nome"])

nomes_intersecao_set = set(nomes_intersecao)

# Apenas CD
nomes_somente_cd = nomes_cd - nomes_intersecao_set

# Apenas SF
nomes_somente_sf = nomes_sf - nomes_intersecao_set

print("Somente CD:", len(nomes_somente_cd))
print("Somente SF:", len(nomes_somente_sf))

# -------------------------
# Adiciona PRNs somente CD
# -------------------------

for nome in nomes_somente_cd:
    data_cd = prn_cd_por_nome.get(nome)

    if not data_cd:
        continue
    print(data_cd)
    p_cd = json_to_proposicao(data_cd)

    materia = Materia(
        id=0,
        casa_iniciadora=p_cd.casa_origem,
        tipo=p_cd.tipo,
        sigla_tipo=p_cd.sigla_tipo,

        proposicao_cd=p_cd,
        proposicao_sf=None,

        transformada_em_norma=data_cd.get(
            "transformado_em_norma", False
        ),

        norma_gerada=json_to_materia(
            p_cd,
            data_cd
        ).norma_gerada
    )

    materias.append(materia)

# -------------------------
# Adiciona PRNs somente SF
# -------------------------

for nome in nomes_somente_sf:
    data_sf = prn_sf_por_nome.get(nome)

    if not data_sf:
        continue
    print(data_sf)
    p_sf = json_to_proposicao(data_sf)

    materia = Materia(
        id=0,
        casa_iniciadora=p_sf.casa_origem,
        tipo=p_sf.tipo,
        sigla_tipo=p_sf.sigla_tipo,

        proposicao_cd=None,
        proposicao_sf=p_sf,

        transformada_em_norma=data_sf.get(
            "transformado_em_norma", False
        ),

        norma_gerada=json_to_materia(
            p_sf,
            data_sf
        ).norma_gerada
    )

    materias.append(materia)

for nome in nomes_intersecao:
    data_cd = prn_cd_por_nome.get(nome)
    data_sf = prn_sf_por_nome.get(nome)
    
    if not data_cd or not data_sf:
        continue
    print(data_cd)
    p_cd = json_to_proposicao(data_cd)
    print(p_cd)
    print(data_sf)

    p_sf = json_to_proposicao(data_sf)
    
    materia = Materia(
        id=0,
        casa_iniciadora=p_cd.casa_origem or p_sf.casa_origem,
        tipo=p_cd.tipo,
        sigla_tipo=p_cd.sigla_tipo,
        
        proposicao_cd=p_cd,
        proposicao_sf=p_sf,
        
        transformada_em_norma=(
            data_cd.get("transformado_em_norma", False) or
            data_sf.get("transformado_em_norma", False)
        ),
        
        norma_gerada=(
            json_to_materia(p_cd, data_cd).norma_gerada
            or json_to_materia(p_sf, data_sf).norma_gerada
        )
    )
    
    materias.append(materia)

""" for p in tqdm(proposicoes_sf):
    if p["sigla_tipo"] in ["PRS"]:
        a = json_to_proposicao(p)

for p in tqdm(proposicoes_cd):
    if p["sigla_tipo"] in ["PRC", "PRF"]:
        print(p)
        a = json_to_proposicao(p)
print(a) """