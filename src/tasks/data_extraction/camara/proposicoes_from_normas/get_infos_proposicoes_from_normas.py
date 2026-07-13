import asyncio
import json
import re
import time
from pathlib import Path
from src.shared.async_collector import AsyncCollector

INPUT_FILE = "data/normas/metadados//proposicoes_origem_normalizadas.json"
OUTPUT_FILE = "data/camara/metadados/info_proposicoes.json"

BASE_URL = "https://dadosabertos.camara.leg.br/api/v2/proposicoes"

PATTERN = re.compile(r"([A-Z]+)\s+(\d+A?)/(\d{4})")


async def main():
    start_time = time.time()

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        proposicoes_origem = json.load(f)

    urls = []
    metadata = []
    resultados = {}

    for urn, prop in proposicoes_origem.items():
        origens = prop.get("origem_final") or []
        casas = prop.get("casas") or [None] * len(origens)

        resultados[urn] = []

        for origem, casa in zip(origens, casas):
            match = PATTERN.search(origem)

            if not match:
                print(f"⚠️ Não foi possível interpretar: {origem}")
                continue

            sigla, numero, ano = match.groups()

            registro_base = {
                "origem": origem,
                "casa": casa,
                "sigla": sigla,
                "numero": numero,
                "ano": ano,
            }

            # Se for claramente Senado, não consulta Câmara
            if casa == "SF":
                resultados[urn].append({
                    **registro_base,
                    "resultado": []
                })
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

            metadata.append({
                "urn": urn,
                "url": url,
                **registro_base
            })

    print(f"🚀 Coletando {len(urls)} proposições da Câmara...")

    collector = AsyncCollector(
        max_concurrent=15,
        retries=3
    )

    raw_results = await collector.collect(urls)

    for meta, res in zip(metadata, raw_results):
        urn = meta["urn"]

        resultados[urn].append({
            **meta,
            "resultado": res
        })

    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time

    print("\n✅ Processo concluído!")
    print(f"📊 Total de URNs: {len(resultados)}")
    print(f"💾 Salvo em: {OUTPUT_FILE}")
    print(f"⏱️ Tempo total: {elapsed:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())