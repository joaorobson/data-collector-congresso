import asyncio
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import aiohttp

from src.shared.async_collector import AsyncCollector

INPUT_FILE = "data/normas/metadados/proposicoes_origem_normalizadas.json"
OUTPUT_FILE = "data/camara/metadados/proposicoes.json"

BASE_URL = "https://dadosabertos.camara.leg.br/api/v2/proposicoes"
OLD_BASE_URL = "https://www.camara.leg.br/SitCamaraWS/Proposicoes.asmx/ObterProposicao"

PATTERN = re.compile(r"([A-Z]+)\s+(\d+A?)/(\d{4})")


def precisa_coletar(resultado_existente) -> bool:
    """
    Verifica se um registro precisa ser coletado novamente.
    """

    if not resultado_existente:
        return True

    res = resultado_existente.get("resultado")

    if res is None or res == []:
        return True

    if isinstance(res, dict):
        if res.get("erro"):
            return True

        if not res.get("dados"):
            return True

    return False


def resposta_sem_dados(resposta):
    """
    Verifica se a resposta da API v2 não encontrou nenhuma proposição.
    """

    if not resposta:
        return True

    if resposta.get("erro"):
        return True

    resultado = resposta.get("resultado")

    if not resultado:
        return True

    if not isinstance(resultado, dict):
        return True

    return len(resultado.get("dados", [])) == 0


async def buscar_id_api_antiga(session, sigla, numero, ano):
    """
    Consulta a API antiga e retorna o idProposicao.
    """

    url = (
        f"{OLD_BASE_URL}?"
        f"tipo={sigla}&"
        f"numero={numero}&"
        f"ano={ano}"
    )

    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None

            xml = await resp.text()

            root = ET.fromstring(xml)

            id_prop = root.findtext("idProposicao")

            if id_prop:
                return id_prop.strip()

    except Exception as e:
        print(f"Erro consultando API antiga: {url}")
        print(e)

    return None


async def main():
    start_time = time.time()

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        proposicoes_origem = json.load(f)

    output_path = Path(OUTPUT_FILE)

    resultados = {}

    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            try:
                resultados = json.load(f)
            except json.JSONDecodeError:
                resultados = {}

    urls = []
    metadata = []

    for urn, prop in proposicoes_origem.items():

        origens = prop.get("origem_final") or []
        casas = prop.get("casas") or [None] * len(origens)

        registros_atuais = resultados.get(urn, [])
        novos_registros = []

        for idx, (origem, casa) in enumerate(zip(origens, casas)):

            match = PATTERN.search(origem)

            if not match:
                print(f"⚠ Não foi possível interpretar: {origem}")
                continue

            sigla, numero, ano = match.groups()

            registro_base = {
                "origem": origem,
                "casa": casa,
                "sigla": sigla,
                "numero": numero,
                "ano": ano,
            }

            # Senado não consulta Câmara
            if casa == "SF":
                novos_registros.append(
                    {
                        **registro_base,
                        "resultado": [],
                    }
                )
                continue

            registro_existente = (
                registros_atuais[idx]
                if idx < len(registros_atuais)
                else None
            )

            if registro_existente and not precisa_coletar(registro_existente):
                novos_registros.append(registro_existente)
                continue

            url = (
                f"{BASE_URL}?"
                f"siglaTipo={sigla}&"
                f"numero={numero}&"
                f"ano={ano}&"
                f"ordem=ASC&"
                f"ordenarPor=id"
            )

            urls.append(url)

            metadata.append(
                {
                    "urn": urn,
                    "index": idx,
                    "url": url,
                    **registro_base,
                }
            )

            novos_registros.append(
                {
                    "urn": urn,
                    "url": url,
                    **registro_base,
                    "resultado": [],
                }
            )

        resultados[urn] = novos_registros

    if urls:

        print(f"🚀 Coletando {len(urls)} proposições...")

        collector = AsyncCollector(
            max_concurrent=15,
            retries=3,
        )

        raw_results = await collector.collect(urls)

        print("🔎 Verificando resultados vazios na API v2...")

        async with aiohttp.ClientSession() as session:

            for i, (meta, res) in enumerate(zip(metadata, raw_results)):

                if not resposta_sem_dados(res):
                    continue

                print(
                    f"↪ API antiga: "
                    f"{meta['sigla']} {meta['numero']}/{meta['ano']}"
                )

                id_prop = await buscar_id_api_antiga(
                    session,
                    meta["sigla"],
                    meta["numero"],
                    meta["ano"],
                )

                if not id_prop:
                    continue

                nova_url = f"{BASE_URL}/{id_prop}"

                print(f"   Encontrado id {id_prop}. Consultando API v2...")

                novo_resultado = await collector.collect([nova_url])

                if novo_resultado:
                    raw_results[i] = novo_resultado[0]
                    meta["url"] = nova_url

        for meta, res in zip(metadata, raw_results):

            resultados[meta["urn"]][meta["index"]] = {
                "urn": meta["urn"],
                "url": meta["url"],
                "origem": meta["origem"],
                "casa": meta["casa"],
                "sigla": meta["sigla"],
                "numero": meta["numero"],
                "ano": meta["ano"],
                "resultado": res,
            }

    else:
        print("✅ Nenhuma coleta necessária.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time

    print("\n✅ Processo concluído!")
    print(f"📊 Total de URNs: {len(resultados)}")
    print(f"💾 Arquivo: {OUTPUT_FILE}")
    print(f"⏱ Tempo: {elapsed:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())