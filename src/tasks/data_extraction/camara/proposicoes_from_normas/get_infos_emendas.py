import asyncio
import json
import os
from src.shared.async_collector import AsyncCollector

URL_RELACIONADAS = (
    "https://dadosabertos.camara.leg.br/api/v2/proposicoes/{}/relacionadas"
)


async def main():
    input_path = "data/camara/metadados/info_proposicoes.json"
    tipos_path = "data/camara/sigla_tipos_emendas.json"
    output_path = "data/camara/metadados/emendas_proposicoes.json"

    if not os.path.exists(input_path):
        print(f"❌ Arquivo não encontrado: {input_path}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        proposicoes = json.load(f)

    with open(tipos_path, "r", encoding="utf-8") as f:
        siglas_permitidas = set(json.load(f))

    processos = []

    # input agora é dict por URN
    for urn, props in proposicoes.items():
        for prop in props:
            resultado = prop.get("resultado") or {}

            if not isinstance(resultado, dict):
                continue

            dados = resultado.get("dados", [])

            for item in dados:
                if item.get("id"):
                    processos.append({
                        "urn": urn,
                        "origem": prop["origem"],
                        "id": item["id"],
                        "url": URL_RELACIONADAS.format(item["id"])
                    })

    if not processos:
        print("⚠️ Nenhuma proposição encontrada.")
        return

    urls = [p["url"] for p in processos]

    print(f"🚀 Coletando proposições relacionadas de {len(urls)} proposições...")

    collector = AsyncCollector(
        max_concurrent=10,
        retries=5
    )

    raw_results = await collector.collect(urls)

    # chave = id do processo
    resultados_finais = {}

    for processo, res in zip(processos, raw_results):
        id_processo = str(processo["id"])

        relacionadas = []

        if isinstance(res, dict):
            relacionadas = res.get("dados", [])

            relacionadas = [
                r for r in relacionadas
                if r.get("siglaTipo") in siglas_permitidas
            ]

        resultados_finais[id_processo] = {
            "urn": processo["urn"],
            "origem": processo["origem"],
            "resultado": relacionadas
        }

    print(f"\n✅ Coleta concluída!")
    print(f"📦 Proposições processadas: {len(resultados_finais)}")

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