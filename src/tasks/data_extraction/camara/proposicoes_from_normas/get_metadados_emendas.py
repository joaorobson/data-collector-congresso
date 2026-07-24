import asyncio
import json
import os

from src.shared.async_collector import AsyncCollector

URL_RELACIONADAS = (
    "https://dadosabertos.camara.leg.br/api/v2/proposicoes/{}/relacionadas"
)


async def main():

    input_path = "data/camara/metadados/proposicoes.json"
    tipos_path = "data/camara/metadados/sigla_tipos_emendas.json"
    output_path = "data/camara/metadados/emendas.json"

    if not os.path.exists(input_path):
        print(f"❌ Arquivo não encontrado: {input_path}")
        return

    if not os.path.exists(tipos_path):
        print(f"❌ Arquivo não encontrado: {tipos_path}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        proposicoes = json.load(f)

    with open(tipos_path, "r", encoding="utf-8") as f:
        siglas_permitidas = set(json.load(f))

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
    # Monta lista de proposições pendentes
    # -------------------------------------------------------

    for urn, props in proposicoes.items():

        for prop in props:

            resultado = prop.get("resultado") or {}

            if not isinstance(resultado, dict):
                continue

            dados = resultado.get("dados", [])

            for item in dados:

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
                        "url": URL_RELACIONADAS.format(id_processo),
                    }
                )

    print(f"📋 Proposições pendentes: {len(processos)}")

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

        relacionadas = []

        if resposta["status"] == 200:

            body = resposta["resultado"]

            if isinstance(body, dict):

                relacionadas = body.get("dados", [])

                relacionadas = [
                    r
                    for r in relacionadas
                    if r.get("siglaTipo") in siglas_permitidas
                ]

        resultados[processo["id"]] = {
            "urn": processo["urn"],
            "origem": processo["origem"],
            "status": resposta["status"],
            "erro": resposta["erro"],
            "resultado": relacionadas,
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
    print(f"📦 Proposições processadas: {len(resultados)}")
    print(f"💾 Arquivo salvo em: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())