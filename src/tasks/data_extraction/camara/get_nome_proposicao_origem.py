import asyncio
import json
import os
from src.shared.async_collector import AsyncCollector
import xml.etree.ElementTree as ET

URL_RELACIONADAS = (
    "https://www.camara.leg.br/SitCamaraWS/Proposicoes.asmx/ObterProposicaoPorID?IdProp={}"
)

async def main():
    input_path = "data/camara/infos_proposicoes.json"
    tipos_path = "data/camara/sigla_tipos_emendas.json"
    output_path = "data/camara/nome_origem_proposicoes.json"

    # 1. Carrega proposições
    if not os.path.exists(input_path):
        print(f"❌ Arquivo não encontrado: {input_path}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        proposicoes = json.load(f)

    with open(tipos_path, "r", encoding="utf-8") as f:
        siglas_permitidas = set(json.load(f))

    # 2. Monta URLs
    processos = [
        {
            "id": p["id"],
            "url": URL_RELACIONADAS.format(p["id"])
        }
        for p in proposicoes
        if p.get("id")
    ]

    if not processos:
        print("⚠️ Nenhuma proposição encontrada.")
        return

    urls = [p["url"] for p in processos]

    print(f"🚀 Coletando proposições relacionadas de {len(urls)} proposições...")

    # 3. Coleta assíncrona
    collector = AsyncCollector(
        max_concurrent=10,
        retries=5
    )


    raw_results = await collector.collect(urls)
    # 4. Salva como dict:
    # {
    #   "12345": [...],
    #   "67890": [...]
    # }
    resultados_finais = {}

    for processo, res in zip(processos, raw_results):

        id_processo = str(processo["id"])
        nome_origem = None

        if isinstance(res, str):  # 🔥 agora é XML string
            try:
                root = ET.fromstring(res)

                elem = root.find("nomeProposicaoOrigem")
                if elem is not None and elem.text:
                    nome_origem = elem.text.strip()

            except Exception as e:
                print(f"⚠️ Erro ao processar XML {id_processo}: {e}")

        resultados_finais[id_processo] = nome_origem

    print(f"\n✅ Coleta concluída!")
    print(f"📦 Proposições processadas: {len(resultados_finais)}")

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