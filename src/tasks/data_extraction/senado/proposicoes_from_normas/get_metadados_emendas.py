import asyncio
import json
import os

from src.shared.async_collector import AsyncCollector

URL_EMENDAS = (
    "https://legis.senado.leg.br/dadosabertos/processo/emenda"
    "?idProcesso={}&v=1"
)


async def main():

    input_path = "data/senado/metadados/proposicoes.json"
    output_path = "data/senado/metadados/emendas.json"

    if not os.path.exists(input_path):
        print(f"❌ Arquivo não encontrado: {input_path}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        proposicoes = json.load(f)

    # -------------------------------------------------------
    # Carrega resultado anterior (execução incremental)
    # -------------------------------------------------------

    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            resultados = json.load(f)
    else:
        resultados = {}

    processos = []

    # -------------------------------------------------------
    # Monta lista de processos pendentes
    # -------------------------------------------------------

    for urn, props in proposicoes.items():

        for prop in props:

            resultado = prop.get("resultado") or []

            if isinstance(resultado, dict):
                resultado = [resultado]

            for item in resultado:

                id_processo = str(item.get("id"))

                if not id_processo:
                    continue

                existente = resultados.get(id_processo)

                # Já possui resultado -> não consulta novamente
                if existente and existente.get("resultado"):
                    continue

                processos.append(
                    {
                        "id": id_processo,
                        "urn": urn,
                        "origem": prop["origem"],
                        "url": URL_EMENDAS.format(id_processo),
                    }
                )

    print(f"📋 Processos pendentes: {len(processos)}")

    if not processos:
        print("✅ Tudo já processado.")
        return

    collector = AsyncCollector(
        max_concurrent=10,
        retries=5,
    )

    respostas = await collector.collect(
        [p["url"] for p in processos]
    )

    # -------------------------------------------------------
    # Processa respostas
    # -------------------------------------------------------

    for processo, resposta in zip(processos, respostas):

        emendas = []

        if resposta["status"] == 200:

            body = resposta["resultado"]

            if isinstance(body, list):
                emendas = body

            elif isinstance(body, dict):
                emendas = [body]

        resultados[processo["id"]] = {
            "urn": processo["urn"],
            "origem": processo["origem"],
            "status": resposta["status"],
            "erro": resposta["erro"],
            "resultado": emendas,
        }

    # -------------------------------------------------------
    # Salva resultado
    # -------------------------------------------------------

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            resultados,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("\n✅ Coleta concluída!")
    print(f"📦 Processos processados: {len(resultados)}")
    print(f"💾 Arquivo salvo em: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())