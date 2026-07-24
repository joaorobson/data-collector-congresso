import asyncio
import json
import os

from src.shared.async_collector import AsyncCollector

URL_DOCUMENTOS = (
    "https://legis.senado.leg.br/dadosabertos/processo/documento"
    "?idProcesso={}&v=1"
)


async def main():

    input_path = "data/senado/metadados/proposicoes.json"
    tipos_path = "data/senado/metadados/sigla_tipos_relatorios_e_pareceres.json"
    output_path = "data/senado/metadados/relatorios_e_pareceres.json"

    if not os.path.exists(input_path):
        print(f"❌ Arquivo não encontrado: {input_path}")
        return

    with open(input_path, encoding="utf-8") as f:
        proposicoes = json.load(f)

    if not os.path.exists(tipos_path):
        print(f"❌ Arquivo não encontrado: {tipos_path}")
        return

    with open(tipos_path, encoding="utf-8") as f:
        siglas_permitidas = set(json.load(f))

    # -----------------------------------------------------
    # Carrega resultado anterior
    # -----------------------------------------------------

    if os.path.exists(output_path):
        with open(output_path, encoding="utf-8") as f:
            resultados_finais = json.load(f)
    else:
        resultados_finais = {}

    processos = []

    for urn, itens in proposicoes.items():

        registro = resultados_finais.get(urn)

        # Se já possui resultado preenchido, não processa novamente
        if registro and registro.get("resultado"):
            continue

        for proposicao in itens:

            resultados = proposicao.get("resultado") or []

            if isinstance(resultados, dict):
                resultados = [resultados]

            for resultado in resultados:

                id_processo = resultado.get("id")

                if not id_processo:
                    continue

                processos.append(
                    {
                        "urn": urn,
                        "id": id_processo,
                        "url": URL_DOCUMENTOS.format(id_processo),
                    }
                )

    print(f"📋 URNs pendentes: {len(processos)}")

    if not processos:
        print("✅ Nada para processar.")
        return

    collector = AsyncCollector(
        max_concurrent=10,
        retries=5,
    )

    respostas = await collector.collect(
        [p["url"] for p in processos]
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    for processo, resposta in zip(processos, respostas):

        documentos = resposta["resultado"]

        if isinstance(documentos, dict):
            documentos = [documentos]

        elif not isinstance(documentos, list):
            documentos = []

        documentos_filtrados = [
            doc
            for doc in documentos
            if doc.get("siglaTipo") in siglas_permitidas
        ]

        resultados_finais[processo["urn"]] = {
            "status": resposta["status"],
            "erro": resposta["erro"],
            "resultado": documentos_filtrados,
        }

        # checkpoint
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                resultados_finais,
                f,
                ensure_ascii=False,
                indent=2,
            )

    print(f"\n✅ Coleta concluída.")
    print(f"📦 Total salvo: {len(resultados_finais)}")
    print(f"💾 Arquivo: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())