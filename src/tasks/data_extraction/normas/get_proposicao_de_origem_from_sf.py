import os
import json
import asyncio
import random

import aiohttp
from tqdm.asyncio import tqdm

CONCORRENCIA = 5
MAX_RETRIES = 8
BASE_BACKOFF = 2

INPUT_FILE = "data/normas/metadados/normas.json"
OUTPUT_FILE = "data/normas/metadados/proposicoes_de_origem_da_norma_from_sf.json"

URL_NORMA = "https://legis.senado.gov.br/dadosabertos/processo?tipoNorma={}&numeroNorma={}&anoNorma={}&v=1"
URL_MPVS = "https://legis.senado.gov.br/dadosabertos/processo?sigla=MPV&numero={}&ano={}&v=1"
URL_PROCESSO = "https://legis.senado.leg.br/dadosabertos/processo/{}?v=1"

tipo_para_sigla = {
    "Lei": "LEI",
    "Decreto Legislativo": "DLG",
    "Emenda Constitucional": "EMC",
    "Medida Provisória": "MPV",
    "Lei Complementar": "LCP"
}


def extrair_dados_norma(norma):
    tipo = norma["tipo"]

    if tipo != "Resolução":
        tipo_sigla = tipo_para_sigla.get(tipo)
    elif norma["titulo"].startswith("Resolução do Senado Federal"):
        tipo_sigla = "RSF"
    elif (
        norma["titulo"].endswith("CN")
        or norma["titulo"].startswith("Resolução do Congresso Nacional")
    ):
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


async def consultar_processo(session, processo_id):
    try:
        async with session.get(URL_PROCESSO.format(processo_id)) as response:
            if response.status != 200:
                return None

            return await response.json()

    except Exception:
        return None


async def fetch_norma(session, semaforo, norma):
    async with semaforo:
        try:
            dados = extrair_dados_norma(norma)

            if not dados:
                return {
                    "urn": norma["urn"],
                    "tipo": norma["tipo"],
                    "erro": "Tipo não suportado",
                }

            if norma["tipo"] != "Medida Provisória":
                url = URL_NORMA.format(
                    dados["tipo_sigla"],
                    dados["numero_norma"],
                    dados["ano_norma"],
                )
            else:
                url = URL_MPVS.format(
                    dados["numero_norma"],
                    dados["ano_norma"],
                )

        except Exception as e:
            return {
                "urn": norma.get("urn"),
                "tipo": norma.get("tipo"),
                "erro": f"Erro ao extrair dados: {e}",
            }

        for tentativa in range(MAX_RETRIES):
            try:
                async with session.get(url) as response:

                    if response.status == 200:
                        try:
                            data = await response.json()
                        except Exception:
                            data = await response.text()

                        if isinstance(data, list):
                            for processo in data:
                                processo_id = processo.get("id")

                                if not processo_id:
                                    continue

                                proc_json = await consultar_processo(
                                    session,
                                    processo_id,
                                )

                                if not proc_json:
                                    continue

                                processo[
                                    "identificacaoProcessoInicial"
                                ] = proc_json.get(
                                    "identificacaoProcessoInicial"
                                )

                                processo[
                                    "siglaCasaIniciadora"
                                ] = proc_json.get(
                                    "siglaCasaIniciadora"
                                )

                                if "outrosNumeros" in proc_json:
                                    processo["outrosNumeros"] = proc_json[
                                        "outrosNumeros"
                                    ]

                        return {
                            "urn": dados["urn"],
                            "tipo": dados["tipo"],
                            "numero_norma": dados["numero_norma"],
                            "ano_norma": dados["ano_norma"],
                            "url": url,
                            "status_code": 200,
                            "resultado": data,
                        }

                    if response.status == 429:
                        retry_after = response.headers.get("Retry-After")

                        if retry_after:
                            espera = int(retry_after)
                        else:
                            espera = BASE_BACKOFF * (2**tentativa)

                        espera += random.uniform(0, 1)

                        print(f"429 -> aguardando {espera:.2f}s")
                        await asyncio.sleep(espera)
                        continue

                    texto = await response.text()

                    return {
                        "urn": dados["urn"],
                        "tipo": dados["tipo"],
                        "url": url,
                        "status_code": response.status,
                        "erro": texto,
                    }

            except aiohttp.ClientError as e:
                if tentativa == MAX_RETRIES - 1:
                    return {
                        "urn": dados["urn"],
                        "tipo": dados["tipo"],
                        "erro": str(e),
                    }

                espera = BASE_BACKOFF * (2**tentativa)
                await asyncio.sleep(espera)

        return {
            "urn": dados["urn"],
            "tipo": dados["tipo"],
            "erro": "Máximo de retries excedido",
        }


async def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        normas = json.load(f)

    # Carrega resultados existentes indexados pela URN
    resultados = {}

    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            for r in json.load(f):
                resultados[r["urn"]] = r

    resultados_existentes = {
        urn
        for urn, r in resultados.items()
        if (
            r.get("status_code") == 200
            and r.get("resultado")
        )
    }

    print("Resultados já processados:", len(resultados_existentes))

    print(set(i["tipo"] for i in normas))

    normas_filtradas = [
        n
        for n in normas
        if not n["titulo"].startswith("Resolução da Câmara dos Deputados")
    ]

    print("Normas elegíveis:", len(normas_filtradas))

    semaforo = asyncio.Semaphore(CONCORRENCIA)

    timeout = aiohttp.ClientTimeout(total=60)
    connector = aiohttp.TCPConnector(limit=CONCORRENCIA)

    async with aiohttp.ClientSession(
        timeout=timeout,
        connector=connector,
    ) as session:

        tarefas = []

        for norma in normas_filtradas:
            if norma["urn"] in resultados_existentes:
                continue

            tarefas.append(
                fetch_norma(
                    session,
                    semaforo,
                    norma,
                )
            )

        print("Consultando:", len(tarefas))

        for future in tqdm.as_completed(
            tarefas,
            total=len(tarefas),
        ):
            resultado = await future

            # Sempre substitui o resultado anterior da mesma URN
            resultados[resultado["urn"]] = resultado

    resultados_ordenados = sorted(
        resultados.values(),
        key=lambda x: x["urn"]
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            resultados_ordenados,
            f,
            indent=4,
            ensure_ascii=False,
        )

    total_ok = sum(
        r.get("status_code") == 200
        for r in resultados_ordenados
    )

    print(f"Total salvo: {len(resultados_ordenados)}")
    print(f"Sucesso: {total_ok}")

if __name__ == "__main__":
    asyncio.run(main())