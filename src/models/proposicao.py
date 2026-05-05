from pydantic import BaseModel
from typing import List, Optional
from enum import Enum
from datetime import datetime

class Casa(Enum):
    CAMARA = "Câmara dos Deputados"
    SENADO = "Senado Federal"
    CONGRESSO = "Congresso Nacional"

class Autor(BaseModel):
    nome: str
    tipo: str
    uf: Optional[str] = None
    sexo: Optional[str] = None

class Tipo(Enum):
    PEC = "Proposta de Emenda à Constituição"
    PL = "Projeto de Lei"
    PLP = "Projeto de Lei Complementar"
    PDG = "Proposta de Delegação Legislativa"
    PR = "Projeto de Resolução"
    PD = "Projeto de Decreto Legislativo"
    MPV = "Medida Provisória"

class SiglaTipo(Enum):
    PEC = "PEC"
    PL = "PL"
    PLP = "PLP"
    PDG = "PDG"
    PR = "PR"
    PD = "PD"
    MPV = "MPV"

class Norma(BaseModel):
    nome: str
    ano: int
    ementa: str
    data_publicacao: datetime
    
class Emenda(BaseModel):
    id: int
    numero: int
    uri: str
    data_apresentacao: datetime

class Relatorio(BaseModel):
    id: int
    numero: int
    uri: str
    data_apresentacao: datetime

class Proposicao(BaseModel):
    id: int
    uri: str
    ano: int
    nome: str
    nome_inicial: str
    palavras_chave: List[str]
    tipo: Tipo
    sigla_tipo: SiglaTipo
    autoria: List[Autor]
    situacao_atual: str
    em_tramitacao: bool
    data_apresentacao: datetime
    casa_atual: Casa
    casa_origem: Casa
    ementa: str
    emendas: Optional[List[Emenda]] = None
    relatorios: Optional[List[Relatorio]] = None


class Materia(BaseModel):
    id: int
    casa_inicadora: Casa
    tipo: Tipo
    sigla_tipo: SiglaTipo
    proposicao_sf: Optional[Proposicao]
    proposicao_cd: Optional[Proposicao]
    transformada_em_norma: bool
    norma_gerada: Optional[Norma]