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

    # ------------------------------------------------------------------
    # Carrega proposições
    # ------------------------------------------------------------------
    if not os.path.exists(input_path):
        print(f"❌ Arquivo não encontrado: {input_path}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        proposicoes = json.load(f)

    # ------------------------------------------------------------------
    # Carrega siglas permitidas
    # ------------------------------------------------------------------
    if not os.path.exists(tipos_path):
        print(f"❌ Arquivo não encontrado: {tipos_path}")
        return

    with open(tipos_path, "r", encoding="utf-8") as f:
        siglas_permitidas = set(json.load(f))

    # ------------------------------------------------------------------
    # Monta lista de processos
    # ------------------------------------------------------------------
    processos = []

    for urn, itens in proposicoes.items():

        if not itens:
            continue

        for proposicao in itens:

            resultados = proposicao.get("resultado", [])

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

    if not processos:
        print("⚠️ Nenhum processo encontrado.")
        return

    urls = [p["url"] for p in processos]

    print(f"🚀 Coletando documentos de {len(urls)} processos...")

    # ------------------------------------------------------------------
    # Coleta assíncrona
    # ------------------------------------------------------------------
    collector = AsyncCollector(
        max_concurrent=10,
        retries=5,
    )

    raw_results = await collector.collect(urls)

    # ------------------------------------------------------------------
    # Processa resultados
    # ------------------------------------------------------------------
    resultados_finais = {}

    for processo, res in zip(processos, raw_results):

        documentos = []

        if isinstance(res, list):
            documentos = res

        elif isinstance(res, dict):
            # Alguns endpoints retornam diretamente um objeto
            documentos = [res]

        documentos_filtrados = [
            doc
            for doc in documentos
            if doc.get("siglaTipo") in siglas_permitidas
        ]

        # Caso uma URN possua mais de um processo, agrega todos
        resultados_finais.setdefault(processo["urn"], []).extend(
            documentos_filtrados
        )

    print("\n✅ Coleta concluída!")
    print(f"📦 URNs processadas: {len(resultados_finais)}")

    # ------------------------------------------------------------------
    # Salva JSON
    # ------------------------------------------------------------------
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            resultados_finais,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"💾 Arquivo salvo em: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())