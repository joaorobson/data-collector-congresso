import json
from src.models.proposicao import Autor, Tipo, Proposicao, Materia, Norma, Emenda, Relatorio
import pandas as pd
from datetime import datetime
from typing import Dict, Any
from tqdm import tqdm

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
    if sigla in ["PRC", "PRS"]:
        return "PR"
    return sigla

def senado_json_to_proposicao(data: Dict[str, Any]) -> Proposicao:
    p = Proposicao(
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

    m = Materia(
        id=0,
        casa_iniciadora=p.casa_atual,
        tipo=p.tipo,
        sigla_tipo=p.sigla_tipo,
        proposicao_sf=p,
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
    return m


with open("data/senado/proposicoes_normalizadas.json", "r", encoding="utf-8") as f:
    proposicoes_sf = json.load(f)

with open("data/camara/proposicoes_normalizadas.json", "r", encoding="utf-8") as f:
    proposicoes_cd = json.load(f)

for p in tqdm(proposicoes_sf):
    if p["sigla_tipo"] in ["PRS"]:
        a = senado_json_to_proposicao(p)

for p in tqdm(proposicoes_cd):
    if p["sigla_tipo"] in ["PRC"]:
        print(p)
        a = senado_json_to_proposicao(p)
print(a)