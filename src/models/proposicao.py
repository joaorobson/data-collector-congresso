from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Annotated
from enum import Enum
from datetime import datetime

class Casa(Enum):
    CAMARA = "Câmara dos Deputados"
    SENADO = "Senado Federal"
    CONGRESSO = "Congresso Nacional"

class TipoProposicao(Enum):
    PEC = "Proposta de Emenda à Constituição"
    PL = "Projeto de Lei"
    PLP = "Projeto de Lei Complementar"
    PDG = "Proposta de Delegação Legislativa"
    PR = "Projeto de Resolução"
    PDL = "Projeto de Decreto Legislativo"
    MPV = "Medida Provisória"
    EMENDA = "Emenda"
    DENUNCIA = "Denúncia"

class TipoAutor(str, Enum):
    CIDADAO = "Cidadão"
    PARLAMENTAR = "Parlamentar"
    ORGAO = "Órgão"
    ENTIDADE = "Entidade"


class CargoParlamentar(str, Enum):
    DEPUTADO = "Deputado"
    SENADOR = "Senador"

class TipoOrgao(str, Enum):
    ORGAO = "Órgão"
    COMISSAO = "Comissão"
    SENADO = "Senado Federal"
    CAMARA = "Câmara dos Deputados"
    MESA = "Mesa"
    CONSELHO = "Conselho"


class TipoEntidade(str, Enum):
    DPU = "DPU"
    MPU = "MPU"
    SOCIEDADE_CIVIL = "Sociedade Civil"
    PODER_EXECUTIVO = "Órgão do Poder Executivo"
    PODER_JUDICIARIO = "Órgão do Poder Judiciário"
    PODER_LEGISLATIVO = "Órgão do Poder Legislativo"
    ORGAO_SENADO = "Órgão do Senado Federal"


class Parlamentar(BaseModel):
    tipo: Literal[TipoAutor.PARLAMENTAR]
    nome: str
    cargo: CargoParlamentar
    uf: str | None = None
    partido: str | None = None


class Orgao(BaseModel):
    tipo: Literal[TipoAutor.ORGAO]
    nome: str
    subtipo: TipoOrgao


class Cidadao(BaseModel):
    tipo: Literal[TipoAutor.CIDADAO]
    nome: str


class Entidade(BaseModel):
    tipo: Literal[TipoAutor.ENTIDADE]
    nome: str
    subtipo: TipoEntidade


Autor = Annotated[
    Parlamentar | Orgao | Cidadao | Entidade,
    Field(discriminator="tipo"),
]

class Emenda(BaseModel):
    numero: int
    id_original: int
    data_apresentacao: datetime
    url_doc: Optional[str] = None
    url_metadados: Optional[str] = None

class Relatorio(BaseModel):
    id_original: int
    url_doc: Optional[str] = None
    url_metadados: Optional[str] = None
    data_apresentacao: datetime

class Proposicao(BaseModel):
    id_original: Optional[int] = None
    ano: Optional[int] = None
    nome: Optional[str] = None
    tipo: Optional[TipoProposicao] = None
    casa_atual: Casa
    casa_origem: Casa
    url_doc: Optional[str] = None
    url_metadados: Optional[str] = None
    autoria: Optional[List[Autor]] = None
    data_apresentacao: Optional[datetime] = None
    ementa: Optional[str] = None
    emendas: Optional[List[Emenda]] = None
    relatorios: Optional[List[Relatorio]] = None