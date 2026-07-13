import asyncio
import json
import os
from src.shared.async_collector import AsyncCollector


async def main():
    input_path = 'data/senado/metadados/info_proposicoes.json'
    output_path = 'data/senado/metadados/detalhes_proposicoes.json'

    if not os.path.exists(input_path):
        print(f"❌ Arquivo não encontrado: {input_path}")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        proposicoes_base = json.load(f)

    base_url = "https://legis.senado.leg.br/dadosabertos/processo/{}?v=1"

    urls = []
    metadata = []

    # proposicoes_base agora é dict: {urn: [proposicoes]}
    for urn, proposicoes in proposicoes_base.items():
        if not isinstance(proposicoes, list):
            continue

        for prop in proposicoes:
            resultado = prop.get("resultado")

            if not resultado:
                continue

            # Senado normalmente retorna lista ou objeto com id
            if isinstance(resultado, list):
                for item in resultado:
                    if "id" in item:
                        urls.append(base_url.format(item["id"]))
                        metadata.append({
                            "urn": urn,
                            "id": item["id"]
                        })

            elif isinstance(resultado, dict) and "id" in resultado:
                urls.append(base_url.format(resultado["id"]))
                metadata.append({
                    "urn": urn,
                    "id": resultado["id"]
                })

    if not urls:
        print("⚠️ Nenhuma URL gerada.")
        return

    print(f"🚀 Coletando detalhes de {len(urls)} processos legislativos...")

    collector = AsyncCollector(max_concurrent=10, retries=5)
    raw_results = await collector.collect(urls)

    detalhes_finais = {}

    for meta, res in zip(metadata, raw_results):
        urn = meta["urn"]

        if urn not in detalhes_finais:
            detalhes_finais[urn] = []

        if res and isinstance(res, dict):
            conteudo = res.get("Processo", res)

            detalhes_finais[urn].append({
                "id": meta["id"],
                "detalhes": conteudo
            })

    print(f"\n✅ Coleta concluída!")
    print(f"📊 URNs processadas: {len(detalhes_finais)}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(detalhes_finais, f, ensure_ascii=False, indent=2)

    print(f"💾 Resultados salvos em: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())