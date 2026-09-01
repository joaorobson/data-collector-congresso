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
    id_original: int
    url_doc: str
    url_metadados: str
    ano: int
    nome: str
    tipo: Tipo
    sigla_tipo: SiglaTipo
    autoria: List[Autor]
    data_apresentacao: datetime
    casa_atual: Casa
    casa_origem: Casa
    ementa: str
    emendas: Optional[List[Emenda]] = None
    relatorios: Optional[List[Relatorio]] = None