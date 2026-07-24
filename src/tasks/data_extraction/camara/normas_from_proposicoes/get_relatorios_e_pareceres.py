import asyncio
import json
import os
import random

import aiohttp
from tqdm.asyncio import tqdm

# Configurações
MAX_CONCURRENT_DOWNLOADS = 2
RETRIES = 8

TIMEOUT = aiohttp.ClientTimeout(
    total=300,
    connect=30,
    sock_connect=30,
    sock_read=300,
)


async def baixar_pdf(session, proposicao, url, caminho_destino, semaphore):
    """Baixa um PDF com retentativas e backoff exponencial."""

    async with semaphore:

        # Se já existe e não está vazio, não baixa novamente
        if (
            os.path.isfile(caminho_destino)
            and os.path.getsize(caminho_destino) > 0
        ):
            return True

        for tentativa in range(1, RETRIES + 1):

            try:
                async with session.get(url) as response:

                    if response.status != 200:
                        raise aiohttp.ClientResponseError(
                            response.request_info,
                            response.history,
                            status=response.status,
                            message=response.reason,
                        )

                    with open(caminho_destino, "wb") as f:
                        async for chunk in response.content.iter_chunked(64 * 1024):
                            f.write(chunk)

                    # Verifica se realmente foi salvo
                    if os.path.getsize(caminho_destino) == 0:
                        raise IOError("Arquivo vazio.")

                    return True

            except (
                aiohttp.ClientConnectionError,
                aiohttp.ServerDisconnectedError,
                aiohttp.ClientPayloadError,
                aiohttp.ClientResponseError,
                aiohttp.ClientOSError,
                asyncio.TimeoutError,
                OSError,
            ) as e:

                espera = min(60, (2 ** tentativa) + random.random())

                print(
                    f"⚠️ [{proposicao}] "
                    f"Tentativa {tentativa}/{RETRIES} "
                    f"({type(e).__name__}: {e}) "
                    f"- nova tentativa em {espera:.1f}s"
                )

                # Remove arquivo parcialmente baixado
                try:
                    if os.path.exists(caminho_destino):
                        os.remove(caminho_destino)
                except Exception:
                    pass

                await asyncio.sleep(espera)

            except Exception as e:

                print(
                    f"❌ Erro inesperado em {proposicao}: "
                    f"{type(e).__name__}: {e}"
                )

                try:
                    if os.path.exists(caminho_destino):
                        os.remove(caminho_destino)
                except Exception:
                    pass

                break

        print(f"❌ Falha definitiva: {proposicao}")
        print(f"   URL: {url}")

        return False


async def main():

    input_path = "data/senado/metadados/proposicoes.json"
    output_dir = "data/senado/docs/proposicoes"

    if not os.path.exists(input_path):
        print(f"Arquivo não encontrado: {input_path}")
        return

    os.makedirs(output_dir, exist_ok=True)

    with open(input_path, encoding="utf-8") as f:
        proposicoes = json.load(f)

    downloads = []
    existentes = 0

    for _, props in proposicoes.items():

        if not isinstance(props, list):
            continue

        for prop in props:

            for item in prop.get("resultado", []):

                url = item.get("urlDocumento")
                doc_id = item.get("id")

                if not url or not doc_id:
                    continue

                destino = os.path.join(output_dir, f"{doc_id}.pdf")

                if (
                    os.path.isfile(destino)
                    and os.path.getsize(destino) > 0
                ):
                    existentes += 1
                    continue

                downloads.append(
                    {
                        "url": url,
                        "destino": destino,
                        "proposicao": item.get("identificacao"),
                    }
                )

    total = existentes + len(downloads)

    print(f"📄 Total........: {total}")
    print(f"✅ Existentes...: {existentes}")
    print(f"⬇️ Pendentes....: {len(downloads)}")

    if not downloads:
        print("Todos os PDFs já existem.")
        return

    connector = aiohttp.TCPConnector(
        limit=MAX_CONCURRENT_DOWNLOADS,
        limit_per_host=MAX_CONCURRENT_DOWNLOADS,
        ttl_dns_cache=300,
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/138.0 Safari/537.36"
        )
    }

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

    async with aiohttp.ClientSession(
        connector=connector,
        timeout=TIMEOUT,
        headers=headers,
    ) as session:

        tarefas = [
            baixar_pdf(
                session,
                d["proposicao"],
                d["url"],
                d["destino"],
                semaphore,
            )
            for d in downloads
        ]

        resultados = await tqdm.gather(
            *tarefas,
            total=len(tarefas),
            desc="Baixando PDFs",
        )

    sucessos = sum(resultados)
    falhas = len(downloads) - sucessos

    print("\n✅ Processo concluído!")
    print(f"📄 Total........: {total}")
    print(f"✅ Existentes...: {existentes}")
    print(f"⬇️ Baixados.....: {sucessos}")
    print(f"❌ Falhas.......: {falhas}")


if __name__ == "__main__":
    asyncio.run(main())