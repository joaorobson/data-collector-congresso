import asyncio
import json
import os

from bs4 import BeautifulSoup

from src.shared.async_collector import AsyncCollector


input_path = "data/normas/metadados/normas_com_emendas.json"
output_path = "data/normas/metadados/urls_textos_normas.json"


URL_SENADO = (
    "https://legis.senado.leg.br/dadosabertos/legislacao/urn?urn={}"
)

URL_LEXML = (
    "https://www.lexml.gov.br/urn/{}"
)


async def main():

    with open(input_path, "r", encoding="utf-8") as f:
        normas = json.load(f)


    urns = []
    urls = []
    tipos = []


    # ==========================================
    # Monta lista de consultas
    # ==========================================

    for urn in normas:

        urns.append(urn)

        if "camara.deputados:resolucao" in urn:
            urls.append(URL_LEXML.format(urn))
            tipos.append("camara")

        else:
            urls.append(URL_SENADO.format(urn))
            tipos.append("senado")


    print(f"Consultando {len(urls)} normas...")


    collector = AsyncCollector(
        max_concurrent=10,
        retries=5,
    )


    respostas = await collector.collect(urls)


    resultado = {}

    sem_publicacoes = []
    erros = []

    sucessos = 0


    # ==========================================
    # Processa respostas
    # ==========================================

    for urn, tipo, resposta in zip(
        urns,
        tipos,
        respostas
    ):

        if resposta["status"] != 200:

            resultado[urn] = {
                "status": resposta["status"],
                "erro": resposta.get("erro"),
                "publicacoes": []
            }

            erros.append(urn)
            continue


        publicacoes = []


        # ======================================
        # Câmara dos Deputados (HTML LexML)
        # ======================================

        if tipo == "camara":

            soup = BeautifulSoup(
                resposta["resultado"],
                "html.parser"
            )


            # Procura painel "Outras Publicações"
            for panel in soup.select(
                "div.panel.panel-default"
            ):

                heading = panel.select_one(
                    "div.panel-heading strong"
                )


                if not heading:
                    continue


                if (
                    heading.get_text(strip=True)
                    != "Outras Publicações"
                ):
                    continue


                # Dentro do painel pega Câmara dos Deputados
                link = panel.find(
                    "a",
                    string="Câmara dos Deputados"
                )


                if link:

                    publicacoes.append({
                        "descricao": "Câmara dos Deputados",
                        "url": link["href"]
                    })


                break


        # ======================================
        # Senado (JSON)
        # ======================================

        else:

            body = resposta["resultado"]

            try:

                documentos = (
                    body["DetalheDocumento"]
                    .get("documentos", {})
                    .get("documento", [])
                )


                if isinstance(documentos, dict):
                    documentos = [documentos]


                for documento in documentos:

                    pubs = (
                        documento
                        .get("publicacoes", {})
                        .get("publicacao", [])
                    )


                    if isinstance(pubs, dict):
                        pubs = [pubs]


                    publicacoes.extend(pubs)


            except Exception:

                publicacoes = []


        if not publicacoes:
            sem_publicacoes.append(urn)


        resultado[urn] = {
            "status": 200,
            "erro": None,
            "publicacoes": publicacoes
        }


        sucessos += 1



    # ==========================================
    # Salva arquivo
    # ==========================================

    os.makedirs(
        os.path.dirname(output_path),
        exist_ok=True
    )


    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            resultado,
            f,
            ensure_ascii=False,
            indent=2
        )


    # ==========================================
    # Resumo
    # ==========================================

    print("\n================ RESUMO ================")

    print(f"Sucessos..............: {sucessos}")
    print(f"Sem publicações.......: {len(sem_publicacoes)}")
    print(f"Erros.................: {len(erros)}")


    if sem_publicacoes:

        print("\nURNs sem publicações:")

        for urn in sem_publicacoes:
            print(f" - {urn}")


    if erros:

        print("\nURNs com erro:")

        for urn in erros:
            print(f" - {urn}")


    print(f"\nArquivo salvo em: {output_path}")



if __name__ == "__main__":
    asyncio.run(main())