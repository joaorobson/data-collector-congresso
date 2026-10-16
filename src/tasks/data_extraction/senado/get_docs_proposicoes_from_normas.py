import asyncio
import json
import os
import random

import aiohttp
from tqdm.asyncio import tqdm

# Configurações
MAX_CONCURRENT_DOWNLOADS = 5
RETRIES = 5

TIMEOUT = aiohttp.ClientTimeout(
    total=300,
    connect=30,
    sock_connect=30,
    sock_read=300,
)

async def obter_url_avulso_inicial(session, id_processo):
    url = (
        "https://legis.senado.leg.br/dadosabertos/processo/documento"
        f"?idProcesso={id_processo}"
        "&siglaTipo=AVULSO_INICIAL"
        "&v=1"
    )

    async with session.get(url) as response:

        if response.status != 200:
            return None

        dados = await response.json()

        if not dados:
            return None

        return dados[0].get("urlDocumento")

async def baixar_pdf(session, proposicao, id_processo, url, caminho_destino, semaphore):
    async with semaphore:

        # Já existe
        if (
            os.path.isfile(caminho_destino)
            and os.path.getsize(caminho_destino) > 0
        ):
            return True

        for tentativa in range(1, RETRIES + 1):

            try:

                async with session.get(url) as response:

                    # Documento inexistente
                    if response.status == 404:
                        print(f"404 para {proposicao}. Tentando AVULSO_INICIAL...")

                        nova_url = await obter_url_avulso_inicial(session, id_processo)

                        if nova_url:
                            url = nova_url
                            continue

                        print(f"Não foi encontrado AVULSO_INICIAL para {proposicao}")
                        return False

                    # Outros erros HTTP
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

                        f.flush()
                        os.fsync(f.fileno())

                # Confirma que o arquivo não ficou vazio
                if (
                    not os.path.exists(caminho_destino)
                    or os.path.getsize(caminho_destino) == 0
                ):
                    raise IOError("Arquivo salvo com tamanho zero.")

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

                # Remove arquivo parcial
                try:
                    if os.path.exists(caminho_destino):
                        os.remove(caminho_destino)
                except Exception:
                    pass

                espera = min(60, (2 ** tentativa) + random.random())

                print(
                    f"⚠️ [{proposicao}] "
                    f"Tentativa {tentativa}/{RETRIES} "
                    f"({type(e).__name__}) "
                    f"Nova tentativa em {espera:.1f}s"
                )

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

        print(f"❌ Falha definitiva")
        print(f"   Proposição: {proposicao}")
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
                        "id_processo": item.get("id"),
                    }
                )

    total = existentes + len(downloads)

    print(f"📄 Total........: {total}")
    print(f"✅ Existentes...: {existentes}")
    print(f"⬇️ Pendentes....: {len(downloads)}")

    if not downloads:
        print("Todos os PDFs já foram baixados.")
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
                d["id_processo"],
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