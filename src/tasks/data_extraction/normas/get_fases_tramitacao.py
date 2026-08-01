import asyncio
import json
import os
import random
import aiohttp
from tqdm.asyncio import tqdm

# Configurações de concorrência e resiliência
CONCORRENCIA = 5
MAX_RETRIES = 8
BASE_BACKOFF = 2

INPUT_FILE = "data/normas/metadados/proposicao_inicial.json"
OUTPUT_FILE = "data/normas/metadados/fases_tramitacao.json"

URL_TRAMITACAO = "https://www6ghml.senado.gov.br/dadosmateria/resources/materia-bicameral/detalhes/?sigla={}&numero={}&ano={}&siglaCasa={}"

# Siglas de proposições que NÃO devem ser consultadas
SIGLAS_IGNORADAS = {"MPV", "PRC", "PRS"}


def extrair_parametros(dados_proposicao):
    """Extrai sigla, numero, ano e casa a partir do dicionário de entrada."""
    proposicao = dados_proposicao.get("proposicao", "")
    casa = dados_proposicao.get("casa", "")

    if not proposicao or not casa:
        return None

    try:
        partes = proposicao.strip().split()
        if len(partes) != 2:
            return None

        sigla, numero_ano = partes

        if "/" in numero_ano:
            numero, ano = numero_ano.split("/")
        else:
            return None

        return {
            "sigla": sigla.upper(),
            "numero": numero,
            "ano": ano,
            "siglaCasa": casa,
        }
    except Exception:
        return None


async def fetch_tramitacao(session, semaforo, urn, dados_proposicao):
    params = extrair_parametros(dados_proposicao)

    if not params:
        return {
            "urn": urn,
            "proposicao_origem": dados_proposicao,
            "erro": "Formato de proposição inválido",
        }

    # Bloqueio de segurança para siglas ignoradas
    if params["sigla"] in SIGLAS_IGNORADAS:
        return {
            "urn": urn,
            "proposicao_origem": dados_proposicao,
            "ignorado": True,
            "motivo": f"Tipo de proposição '{params['sigla']}' ignorado pelas regras",
        }

    async with semaforo:
        url = URL_TRAMITACAO.format(
            params["sigla"], params["numero"], params["ano"], params["siglaCasa"]
        )

        for tentativa in range(MAX_RETRIES):
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                        except Exception:
                            data = await response.text()

                        return {
                            "urn": urn,
                            "proposicao_origem": dados_proposicao,
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
                        await asyncio.sleep(espera)
                        continue

                    texto = await response.text()
                    return {
                        "urn": urn,
                        "proposicao_origem": dados_proposicao,
                        "url": url,
                        "status_code": response.status,
                        "erro": texto,
                    }

            except aiohttp.ClientError as e:
                if tentativa == MAX_RETRIES - 1:
                    return {
                        "urn": urn,
                        "proposicao_origem": dados_proposicao,
                        "url": url,
                        "erro": str(e),
                    }

                espera = BASE_BACKOFF * (2**tentativa)
                await asyncio.sleep(espera)

        return {
            "urn": urn,
            "proposicao_origem": dados_proposicao,
            "erro": "Máximo de retries excedido",
        }


async def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Arquivo de entrada não encontrado: {INPUT_FILE}")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        proposicoes = json.load(f)

    # 1. Carrega resultados salvos anteriormente
    resultados = {}
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            try:
                dados_salvos = json.load(f)
                if isinstance(dados_salvos, dict):
                    resultados = dados_salvos
                elif isinstance(dados_salvos, list):
                    for r in dados_salvos:
                        if "urn" in r:
                            resultados[r["urn"]] = r
            except json.JSONDecodeError:
                resultados = {}

    # 2. Identifica o que já está concluído (Sucesso 200 ou Marcado como Ignorado)
    urns_concluidas = set()
    for urn, r in resultados.items():
        status_ok = r.get("status_code") == 200 and r.get("resultado") is not None
        sem_erro = "erro" not in r or r["erro"] is None
        is_ignorado = r.get("ignorado") is True

        if (status_ok and sem_erro) or is_ignorado:
            urns_concluidas.add(urn)

    print(f"Total de proposições na entrada: {len(proposicoes)}")
    print(f"Já concluídas previamente (Sucesso/Ignoradas): {len(urns_concluidas)}")

    semaforo = asyncio.Semaphore(CONCORRENCIA)
    timeout = aiohttp.ClientTimeout(total=60)
    connector = aiohttp.TCPConnector(limit=CONCORRENCIA)

    async with aiohttp.ClientSession(
        timeout=timeout, connector=connector
    ) as session:
        tarefas = []

        for urn, dados in proposicoes.items():
            if urn in urns_concluidas:
                continue

            params = extrair_parametros(dados)
            sigla = params["sigla"] if params else None

            # Caso a sigla deva ser ignorada, registra direto sem criar requisição HTTP
            if sigla in SIGLAS_IGNORADAS:
                resultados[urn] = {
                    "urn": urn,
                    "proposicao_origem": dados,
                    "ignorado": True,
                    "motivo": f"Tipo de proposição '{sigla}' ignorado",
                }
                continue

            tarefas.append(
                fetch_tramitacao(
                    session=session,
                    semaforo=semaforo,
                    urn=urn,
                    dados_proposicao=dados,
                )
            )

        print(f"Consultas HTTP que serão executadas: {len(tarefas)}")

        if tarefas:
            for future in tqdm.as_completed(tarefas, total=len(tarefas)):
                resultado = await future
                resultados[resultado["urn"]] = resultado

    # 3. Salva os resultados ordenados por URN
    resultados_ordenados = {k: resultados[k] for k in sorted(resultados.keys())}

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(resultados_ordenados, f, indent=4, ensure_ascii=False)

    total_ok = sum(
        1
        for r in resultados_ordenados.values()
        if r.get("status_code") == 200 and "erro" not in r
    )
    total_ignorados = sum(
        1 for r in resultados_ordenados.values() if r.get("ignorado") is True
    )
    total_erros = len(resultados_ordenados) - total_ok - total_ignorados

    print("\n--- Resumo Final ---")
    print(f"Total no arquivo '{OUTPUT_FILE}': {len(resultados_ordenados)}")
    print(f"Sucesso (Status 200): {total_ok}")
    print(f"Ignorados (MPV/PRC): {total_ignorados}")
    print(f"Pendentes com Erro: {total_erros}")


if __name__ == "__main__":
    asyncio.run(main())