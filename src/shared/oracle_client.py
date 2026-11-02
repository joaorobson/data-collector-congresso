from urllib.parse import quote

from sqlalchemy import create_engine, text, bindparam
from sqlalchemy.orm import sessionmaker




class OracleClient:
    def __init__(self, username, password, host):
        self.connection_string = f"oracle+oracledb://{username}:{quote(password)}@{host}"
        self.engine = None

    def connect(self):
        self.engine = create_engine(
            self.connection_string,
            pool_pre_ping=True,
            pool_recycle=1800,
            pool_size=5,
            max_overflow=10,
        )
        self.Session = sessionmaker(bind=self.engine)

    def disconnect(self):
        if self.engine:
            self.engine.dispose()
            self.engine = None
            self.Session = None


    def get_urls_download_arquivo_texto_publicado(
        self,
        cod_publicacoes: list[str],
    ) -> dict[str, str]:

        if not cod_publicacoes:
            return {}

        query = (
            text("""
                SELECT DISTINCT
                    cod_instancia,
                    'https://legis.senado.leg.br/sigen/api/instancia/' ||
                    cod_instancia ||
                    '/arquivo-texto-publicado/' ||
                    cod_propriedade ||
                    '/download' AS url
                FROM sigen.viw_detalha_instancia
                WHERE cod_instancia IN :cod_publicacoes
                AND des_propriedade = 'ArquivoTextoPublicado'
            """)
            .bindparams(bindparam("cod_publicacoes", expanding=True))
        )

        with self.Session() as session:
            rows = session.execute(
                query,
                {"cod_publicacoes": cod_publicacoes},
            ).all()

        return {
            str(row.cod_instancia): row.url
            for row in rows
        }
