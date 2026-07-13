import asyncio
import json
import os
from src.shared.async_collector import AsyncCollector

URL_EMENDAS = (
    "https://legis.senado.leg.br/dadosabertos/processo/emenda"
    "?idProcesso={}&v=1"
)


async def main():
    input_path = "data/senado/metadados/info_proposicoes.json"
    output_path = "data/senado/metadados/emendas_proposicoes.json"

    if not os.path.exists(input_path):
        print(f"❌ Arquivo não encontrado: {input_path}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        proposicoes = json.load(f)

    processos = []

    for urn, props in proposicoes.items():
        for prop in props:
            resultado = prop.get("resultado") or []

            if not resultado:
                continue

            for item in resultado:
                if item.get("id"):
                    processos.append({
                        "urn": urn,
                        "origem": prop["origem"],
                        "id": item["id"],
                        "url": URL_EMENDAS.format(item["id"])
                    })

    if not processos:
        print("⚠️ Nenhum processo encontrado.")
        return

    urls = [p["url"] for p in processos]

    print(f"🚀 Coletando emendas de {len(urls)} processos...")

    collector = AsyncCollector(
        max_concurrent=10,
        retries=5
    )

    raw_results = await collector.collect(urls)

    # chave = id do processo
    resultados_finais = {}

    for processo, res in zip(processos, raw_results):
        id_processo = str(processo["id"])

        resultados_finais[id_processo] = {
            "urn": processo["urn"],
            "origem": processo["origem"],
            "resultado": res
        }

    print(f"\n✅ Coleta concluída!")
    print(f"📦 Processos processados: {len(resultados_finais)}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            resultados_finais,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(f"💾 Arquivo salvo em: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())