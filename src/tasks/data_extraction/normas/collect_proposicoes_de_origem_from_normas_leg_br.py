import json
import asyncio
import aiohttp
from tqdm.asyncio import tqdm

URL = "https://normas.leg.br/api/public/normas?urn={}&tipo_documento=maior-detalhe"

CONCORRENCIA = 30
MAX_RETRIES = 3


async def fetch_norma(session, semaforo, urn):

    async with semaforo:

        for tentativa in range(MAX_RETRIES):

            try:

                async with session.get(URL.format(urn)) as response:

                    if response.status == 200:

                        detalhes = await response.json()

                        return {
                            "urn": urn,
                            "status": "ok",
                            "sourceProcess": detalhes.get("sourceProcess") or detalhes.get("legislationSourceProcess")
                        }

                    return {
                        "urn": urn,
                        "status": f"http_{response.status}",
                        "sourceProcess": None
                    }

            except Exception as e:

                if tentativa == MAX_RETRIES - 1:

                    return {
                        "urn": urn,
                        "status": f"erro: {str(e)}",
                        "sourceProcess": None
                    }

                await asyncio.sleep(1)


async def main():

    with open("data/normas/metadados//normas_2010_2025.json", "r", encoding="utf-8") as f:
        normas = json.load(f)

    urns = [
        norma["urn"]
        for norma in normas
        if norma.get("urn")
    ]

    semaforo = asyncio.Semaphore(CONCORRENCIA)

    timeout = aiohttp.ClientTimeout(total=60)

    connector = aiohttp.TCPConnector(limit=CONCORRENCIA)

    resultados = []

    async with aiohttp.ClientSession(
        timeout=timeout,
        connector=connector
    ) as session:

        tarefas = [
            fetch_norma(session, semaforo, urn)
            for urn in urns
        ]

        for future in tqdm.as_completed(tarefas, total=len(tarefas)):

            resultado = await future
            resultados.append(resultado)

    with open(
        "data/normas/metadados//proposicoes_de_origem_da_norma_from_normas_leg_br.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            resultados,
            f,
            indent=4,
            ensure_ascii=False
        )

    total_ok = sum(r["status"] == "ok" for r in resultados)

    print("Total URNs:", len(urns))
    print("Total processados:", len(resultados))
    print("Sucesso:", total_ok)


asyncio.run(main())