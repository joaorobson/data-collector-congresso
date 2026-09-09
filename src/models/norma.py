from pydantic import BaseModel
from typing import List, Optional
from enum import Enum
from datetime import datetime
from .proposicao import Proposicao

class TipoNorma(Enum):
    EMC = "Emenda Constitucional"
    LEI = "Lei"
    LCP = "Lei Complementar"
    LDL = "Lei Delegada"
    RES = "Resolução"
    DLG = "Decreto Legislativo"
    MPV = "Medida Provisória"

class Norma(BaseModel):
    nome: str
    urn: str
    tipo_norma: TipoNorma
    data_publicacao: Optional[datetime] = None
    proposicoes: List[Proposicao]