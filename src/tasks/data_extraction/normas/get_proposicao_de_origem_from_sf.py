import json
import asyncio
import aiohttp
from tqdm.asyncio import tqdm
import random

CONCORRENCIA = 5
MAX_RETRIES = 8
BASE_BACKOFF = 2

URL = "https://legis.senado.gov.br/dadosabertos/processo?tipoNorma={}&numeroNorma={}&anoNorma={}&v=1"
URL_MPVS = "https://legis.senado.gov.br/dadosabertos/processo?sigla=MPV&numero={}&ano={}&v=1"

tipo_para_sigla = {
    "Lei": "LEI",
    "Decreto Legislativo": "DLG",
    "Emenda Constitucional": "EMC",
    "Medida Provisória": "MPV",
}


def extrair_dados_norma(norma):
    tipo = norma["tipo"]

    if tipo != "Resolução":
        tipo_sigla = tipo_para_sigla.get(tipo)
    elif norma["titulo"].startswith("Resolução do Senado Federal"):
        tipo_sigla = "RSF"
    elif norma["titulo"].endswith("CN") or norma["titulo"].startswith("Resolução do Congresso Nacional"):
        tipo_sigla = "RCN"
    else:
        tipo_sigla = None

    if not tipo_sigla:
        return None

    urn = norma["urn"]

    parte_final = urn.split(":")[-1]
    data_norma, numero_norma = parte_final.split(";")
    ano_norma = data_norma[:4]

    return {
        "urn": urn,
        "tipo": tipo,
        "tipo_sigla": tipo_sigla,
        "numero_norma": numero_norma,
        "ano_norma": ano_norma,
    }


async def fetch_norma(session, semaforo, norma):
    async with semaforo:
        try:
            dados = extrair_dados_norma(norma)

            if not dados:
                return {
                    "urn": norma["urn"],
                    "tipo": norma["tipo"],
                    "erro": "Tipo não suportado"
                }

            if norma["tipo"] != "Medida Provisória":
                url = URL.format(
                    dados["tipo_sigla"],
                    dados["numero_norma"],
                    dados["ano_norma"]
                )
            else:
                url = URL_MPVS.format(
                    dados["numero_norma"],
                    dados["ano_norma"]
                )

        except Exception as e:
            return {
                "urn": norma.get("urn"),
                "tipo": norma.get("tipo"),
                "erro": f"Erro ao extrair dados: {str(e)}"
            }

        for tentativa in range(MAX_RETRIES):
            try:
                async with session.get(url) as response:

                    if response.status == 200:
                        try:
                            data = await response.json()
                        except:
                            data = await response.text()

                        return {
                            "urn": dados["urn"],
                            "tipo": dados["tipo"],
                            "numero_norma": dados["numero_norma"],
                            "ano_norma": dados["ano_norma"],
                            "url": url,
                            "status_code": 200,
                            "resultado": data
                        }

                    if response.status == 429:
                        retry_after = response.headers.get("Retry-After")

                        if retry_after:
                            espera = int(retry_after)
                        else:
                            espera = BASE_BACKOFF * (2 ** tentativa)

                        espera += random.uniform(0, 1)

                        print(f"429 -> aguardando {espera:.2f}s")
                        await asyncio.sleep(espera)
                        continue

                    # outros erros HTTP
                    texto = await response.text()

                    return {
                        "urn": dados["urn"],
                        "tipo": dados["tipo"],
                        "url": url,
                        "status_code": response.status,
                        "erro": texto
                    }

            except aiohttp.ClientError as e:
                if tentativa == MAX_RETRIES - 1:
                    return {
                        "urn": dados["urn"],
                        "tipo": dados["tipo"],
                        "erro": str(e)
                    }

                espera = BASE_BACKOFF * (2 ** tentativa)
                await asyncio.sleep(espera)

        return {
            "urn": dados["urn"],
            "tipo": dados["tipo"],
            "erro": "Máximo de retries excedido"
        }


async def main():

    with open(
        "data/normas/metadados/normas_sem_proposicao_origem.json",
        "r",
        encoding="utf-8"
    ) as f:
        normas = json.load(f)

    print(set(i["tipo"] for i in normas))
    normas_filtradas = [n for n in normas if not n["titulo"].startswith("Resolução da Câmara dos Deputados")]

    semaforo = asyncio.Semaphore(CONCORRENCIA)

    timeout = aiohttp.ClientTimeout(total=60)
    connector = aiohttp.TCPConnector(limit=CONCORRENCIA)

    resultados = []

    async with aiohttp.ClientSession(
        timeout=timeout,
        connector=connector
    ) as session:

        tarefas = [
            fetch_norma(session, semaforo, norma)
            for norma in normas_filtradas
        ]

        for future in tqdm.as_completed(tarefas, total=len(tarefas)):
            resultado = await future
            resultados.append(resultado)

    with open(
        "data/normas/metadados/proposicoes_de_origem_da_norma_from_sf.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            resultados,
            f,
            indent=4,
            ensure_ascii=False
        )

    total_ok = sum(
        r.get("status_code") == 200
        for r in resultados
    )

    print("Total processado:", len(resultados))
    print("Sucesso:", total_ok)


asyncio.run(main())