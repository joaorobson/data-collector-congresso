import asyncio
import json
import os
from src.shared.async_collector import AsyncCollector

URL_EMENDAS = (
    "https://legis.senado.leg.br/dadosabertos/processo/emenda"
    "?idProcesso={}&v=1"
)

async def main():
    input_path = "data/senado/infos_proposicoes.json"
    output_path = "data/senado/emendas_proposicoes.json"

    # 1. Carrega proposições
    if not os.path.exists(input_path):
        print(f"❌ Arquivo não encontrado: {input_path}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        proposicoes = json.load(f)

    # 2. Monta URLs
    processos = [
        {
            "id": p["id"],
            "url": URL_EMENDAS.format(p["id"])
        }
        for p in proposicoes
        if p.get("id")
    ]

    if not processos:
        print("⚠️ Nenhum processo encontrado.")
        return

    urls = [p["url"] for p in processos if p["id"]]

    print(f"🚀 Coletando emendas de {len(urls)} processos...")

    # 3. Coleta assíncrona
    collector = AsyncCollector(
        max_concurrent=10,
        retries=5
    )

    raw_results = await collector.collect(urls)

    # 4. Salva como dict:
    # {
    #   "8701679": [...],
    #   "1234567": [...]
    # }

    resultados_finais = {}

    for processo, res in zip(processos, raw_results):

        id_processo = str(processo["id"])

        resultados_finais[id_processo] = res

    print(f"\n✅ Coleta concluída!")
    print(f"📦 Processos processados: {len(resultados_finais)}")

    # 5. Salva JSON
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