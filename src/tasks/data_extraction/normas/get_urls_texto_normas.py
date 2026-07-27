import asyncio
import json
import os
from bs4 import BeautifulSoup
from tqdm import tqdm

from src.shared.async_collector import AsyncCollector
from src.shared.oracle_client import OracleClient

ORACLE_USERNAME = os.environ.get("ORACLE_USERNAME")
ORACLE_PASSWORD = os.environ.get("ORACLE_PASSWORD")
ORACLE_HOST = os.environ.get("ORACLE_HOST")

input_path = "data/normas/metadados/normas_com_emendas.json"
output_path = "data/normas/metadados/urls_textos_normas.json"

URL_SENADO = "https://legis.senado.leg.br/dadosabertos/legislacao/urn?urn={}"
URL_LEXML = "https://www.lexml.gov.br/urn/{}"

# URNs cujo serviço oficial não retorna publicações.
URNS_SEM_PUBLICACOES = {
    "urn:lex:br:federal:decreto.legislativo:2023-08-24;88": {
        "url": "https://www2.camara.leg.br/legin/fed/decleg/2023/decretolegislativo-88-24-agosto-2023-794610-publicacaooriginal-168980-pl.html",
        "anexos": [],
    },
    "urn:lex:br:federal:medida.provisoria:2024-07-09;1240": {
        "url": "https://www2.camara.leg.br/legin/fed/medpro/2024/medidaprovisoria-1240-9-julho-2024-795939-exposicaodemotivos-172574-pe.html",
        "anexos": [],
    },
    "urn:lex:br:senado.federal:resolucao:2022-07-08;15": {
        "url": "https://www2.camara.leg.br/legin/fed/ressen/2022/resolucao-15-8-julho-2022-792957-publicacaooriginal-165695-pl.html",
        "anexos": [],
    },
    "urn:lex:br:federal:lei:2024-06-07;14881": {
        "url": "https://www2.camara.leg.br/legin/fed/lei/2024/lei-14881-7-junho-2024-795740-norma-pl.html",
        "anexos": [
            "https://www2.camara.leg.br/legin/fed/lei/2024/lei-14881-7-junho-2024-795740-anexo-pl.pdf"
        ],
    },
}


def batch_list(items, batch_size=500):
    """Auxiliar para quebrar listas grandes em batches (evita limites do 'IN' do Oracle)."""
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


async def main():
    oracle_client = OracleClient(
        username=ORACLE_USERNAME, password=ORACLE_PASSWORD, host=ORACLE_HOST
    )
    oracle_client.connect()

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            normas = json.load(f)

        # ==========================================
        # Carrega resultados existentes
        # ==========================================
        if os.path.exists(output_path):
            with open(output_path, "r", encoding="utf-8") as f:
                resultado = json.load(f)
        else:
            resultado = {}

        urns = []
        urls = []
        tipos = []

        # ==========================================
        # Monta lista de consultas
        # ==========================================
        for urn in normas:
            if urn in resultado and resultado[urn].get("url"):
                continue

            urns.append(urn)

            if "camara.deputados:resolucao" in urn:
                urls.append(URL_LEXML.format(urn))
                tipos.append("camara")
            else:
                urls.append(URL_SENADO.format(urn))
                tipos.append("senado")

        print(f"Total de normas........: {len(normas)}")
        print(f"Já processadas.........: {len(resultado)}")
        print(f"Consultando............: {len(urls)}")

        if not urls:
            print("\nNenhuma nova URN para consultar.")
            return

        collector = AsyncCollector(
            max_concurrent=10,
            retries=5,
        )

        respostas = await collector.collect(urls)

        # Estrutura para pendências do Oracle:
        # {urn: {"pub_id": "12345", "anx_ids": ["38247481", "38247482"]}}
        pendentes_oracle = {}

        sem_publicacoes = []
        erros = []
        sucessos = 0

        # ==========================================
        # Passo 1: Extração inicial de IDs e URLs HTML
        # ==========================================
        for urn, tipo, resposta in tqdm(
            zip(urns, tipos, respostas), desc="Parsing HTTP"
        ):

            if resposta["status"] != 200:
                resultado[urn] = {
                    "status": resposta["status"],
                    "erro": resposta.get("erro"),
                    "url": None,
                    "anexos": [],
                }
                erros.append(urn)
                continue

            url_publicacao = None
            anexos_fallback = []

            # --------------------------------------
            # Câmara dos Deputados (LexML HTML)
            # --------------------------------------
            if tipo == "camara":
                soup = BeautifulSoup(resposta["resultado"], "html.parser")

                for panel in soup.select("div.panel.panel-default"):
                    heading = panel.select_one("div.panel-heading strong")
                    if (
                        not heading
                        or heading.get_text(strip=True) != "Outras Publicações"
                    ):
                        continue

                    link = panel.find("a", string="Câmara dos Deputados")
                    if link:
                        url_publicacao = link["href"]
                        break

                if not url_publicacao and urn in URNS_SEM_PUBLICACOES:
                    fallback_data = URNS_SEM_PUBLICACOES[urn]
                    url_publicacao = fallback_data.get("url")
                    anexos_fallback = fallback_data.get("anexos", [])

                resultado[urn] = {
                    "status": 200,
                    "erro": None,
                    "url": url_publicacao,
                    "anexos": anexos_fallback,
                }

                if url_publicacao:
                    sucessos += 1
                else:
                    sem_publicacoes.append(urn)

            # --------------------------------------
            # Senado (Extração de IDs do Texto Principal + Anexos)
            # --------------------------------------
            else:
                body = resposta["resultado"]
                pub_id = None
                fallback_vep_id = None
                anx_ids = []

                try:
                    documentos = (
                        body.get("DetalheDocumento", {})
                        .get("documentos", {})
                        .get("documento", [])
                    )

                    if isinstance(documentos, dict):
                        documentos = [documentos]

                    for documento in documentos:
                        pubs = (
                            documento.get("publicacoes", {}).get(
                                "publicacao", []
                            )
                        )

                        if isinstance(pubs, dict):
                            pubs = [pubs]

                        for pub in pubs:
                            tipo_pub = pub.get("tipo")
                            dispositivo = pub.get("dispositivo", "")
                            p_id = str(pub.get("id"))

                            # 1. Busca Publicação Original
                            if tipo_pub == "PUB" and dispositivo.startswith("Publicação Original"):
                                pub_id = p_id

                            # 2. Busca VEP (Fallback para caso não haja Publicação Original)
                            elif tipo_pub == "VEP":
                                fallback_vep_id = p_id

                            # 3. Guarda Anexos
                            elif tipo_pub == "ANX":
                                anx_ids.append(p_id)

                    # Aplica fallback do VEP se necessário
                    if not pub_id and fallback_vep_id:
                        pub_id = fallback_vep_id

                except Exception as e:
                    print(f"\nErro ao extrair JSON para {urn}: {e}")

                # Se achou texto principal ou anexos, adiciona para consulta no Oracle
                if pub_id or anx_ids:
                    pendentes_oracle[urn] = {
                        "pub_id": pub_id,
                        "anx_ids": anx_ids,
                    }
                else:
                    # Tenta fallback para URNs conhecidas
                    if urn in URNS_SEM_PUBLICACOES:
                        fallback_data = URNS_SEM_PUBLICACOES[urn]
                        resultado[urn] = {
                            "status": 200,
                            "erro": None,
                            "url": fallback_data.get("url"),
                            "anexos": fallback_data.get("anexos", []),
                        }
                        if fallback_data.get("url"):
                            sucessos += 1
                        else:
                            sem_publicacoes.append(urn)
                    else:
                        resultado[urn] = {
                            "status": 200,
                            "erro": None,
                            "url": None,
                            "anexos": [],
                        }
                        sem_publicacoes.append(urn)

        # ==========================================
        # Passo 2: Consulta em Lote no Oracle (Senado)
        # ==========================================
        if pendentes_oracle:
            # Reúne todos os IDs (texto principal + anexos) em um único conjunto
            todos_ids_oracle = set()
            for dados in pendentes_oracle.values():
                if dados["pub_id"]:
                    todos_ids_oracle.add(dados["pub_id"])
                for anx_id in dados["anx_ids"]:
                    todos_ids_oracle.add(anx_id)

            print(
                f"\nBuscando URLs no Oracle para {len(todos_ids_oracle)} instâncias do Senado..."
            )

            oracle_urls_map = {}

            # Consulta em lote de 500 em 500 no Oracle
            for chunk_ids in batch_list(list(todos_ids_oracle), batch_size=500):
                res_chunk = (
                    oracle_client.get_urls_download_arquivo_texto_publicado(
                        chunk_ids
                    )
                )
                oracle_urls_map.update(res_chunk)

            # Mapeia as URLs de volta para a estrutura final do JSON
            for urn, dados in pendentes_oracle.items():
                p_id = dados["pub_id"]
                a_ids = dados["anx_ids"]

                # URL principal
                url_principal = oracle_urls_map.get(p_id) if p_id else None

                # URLs dos anexos da API Oracle
                urls_anexos = [
                    oracle_urls_map[anx_id]
                    for anx_id in a_ids
                    if anx_id in oracle_urls_map
                ]

                # Se a busca via Oracle não encontrou a URL principal, verifica o fallback manual
                if not url_principal and urn in URNS_SEM_PUBLICACOES:
                    fallback_data = URNS_SEM_PUBLICACOES[urn]
                    url_principal = fallback_data.get("url")
                    
                    # Estende os anexos com os definidos no fallback (se houver)
                    if fallback_data.get("anexos"):
                        urls_anexos.extend(fallback_data["anexos"])

                resultado[urn] = {
                    "status": 200,
                    "erro": None,
                    "url": url_principal,
                    "anexos": urls_anexos,
                }

                if url_principal:
                    sucessos += 1
                else:
                    sem_publicacoes.append(urn)

        # ==========================================
        # Salva arquivo
        # ==========================================
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)

        # ==========================================
        # Resumo
        # ==========================================
        print("\n================ RESUMO ================")
        print(f"Novos sucessos........: {sucessos}")
        print(f"Sem publicações.......: {len(sem_publicacoes)}")
        print(f"Erros.................: {len(erros)}")
        print(f"Total armazenado......: {len(resultado)}")

        if sem_publicacoes:
            print("\nURNs sem publicações:")
            for urn in sem_publicacoes:
                print(f" - {urn}")

        if erros:
            print("\nURNs com erro:")
            for urn in erros:
                print(f" - {urn}")

        print(f"\nArquivo salvo em: {output_path}")

    finally:
        oracle_client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())