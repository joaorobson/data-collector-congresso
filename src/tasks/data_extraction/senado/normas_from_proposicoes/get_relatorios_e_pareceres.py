import asyncio
import json
import os
from src.shared.async_collector import AsyncCollector

URL_DOCUMENTOS = (
    "https://legis.senado.leg.br/dadosabertos/processo/documento"
    "?idProcesso={}&v=1"
)

async def main():
    input_path = "data/senado/infos_proposicoes.json"
    tipos_path = "data/senado/sigla_tipos_relatorios_e_pareceres.json"
    output_path = "data/senado/relatorios_e_pareceres_proposicoes.json"

    # 1. Carrega proposições
    if not os.path.exists(input_path):
        print(f"❌ Arquivo não encontrado: {input_path}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        proposicoes = json.load(f)

    # 2. Carrega siglas permitidas
    if not os.path.exists(tipos_path):
        print(f"❌ Arquivo não encontrado: {tipos_path}")
        return

    with open(tipos_path, "r", encoding="utf-8") as f:
        siglas_permitidas = set(json.load(f))

    # 3. Monta URLs
    processos = [
        {
            "id": p["id"],
            "url": URL_DOCUMENTOS.format(p["id"])
        }
        for p in proposicoes
        if p.get("id")
    ]

    if not processos:
        print("⚠️ Nenhum processo encontrado.")
        return

    urls = [p["url"] for p in processos]

    print(f"🚀 Coletando documentos de {len(urls)} processos...")

    # 4. Coleta assíncrona
    collector = AsyncCollector(
        max_concurrent=10,
        retries=5
    )

    raw_results = await collector.collect(urls)

    # 5. Estrutura final:
    # {
    #   "8701679": [documentos_filtrados],
    #   "1234567": [documentos_filtrados]
    # }

    resultados_finais = {}

    for processo, res in zip(processos, raw_results):

        id_processo = str(processo["id"])

        documentos = []

        # retorno direto em lista
        if isinstance(res, list):
            documentos = res

        # fallback
        elif isinstance(res, dict):
            documentos = []

        # garante lista
        if isinstance(documentos, dict):
            documentos = [documentos]

        # filtra por siglaTipo
        documentos_filtrados = [
            d for d in documentos
            if d.get("siglaTipo") in siglas_permitidas
        ]

        resultados_finais[id_processo] = documentos_filtrados

    print(f"\n✅ Coleta concluída!")
    print(f"📦 Processos processados: {len(resultados_finais)}")

    # 6. Salva JSON
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