import asyncio
import json
import os
import xml.etree.ElementTree as ET

from src.shared.async_collector import AsyncCollector


URL = "https://www.camara.leg.br/SitCamaraWS/Proposicoes.asmx/ObterProposicaoPorID?IdProp={}"


def strip_namespace(root):
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]


def find_text(root, tag):
    elem = root.find(f".//{tag}")
    if elem is not None and elem.text:
        texto = elem.text.strip()
        return texto if texto else None
    return None


def extrair_nome_norma(situacao):
    """
    Ex:
    'Tranformada no(a) Resolução da Câmara dos Deputados 21/2021'
    -> 'Resolução da Câmara dos Deputados 21/2021'
    """
    prefixo = "Tranformada no(a)"

    if situacao and situacao.startswith(prefixo):
        return situacao.replace(prefixo, "").strip()

    return None


async def main():
    input_path = "data/normas/metadados//infos_projetos_resolucao_cd.json"
    output_path = "data/normas/metadados//projetos_resolucao_cd_transf_norma.json"

    with open(input_path, "r", encoding="utf-8") as f:
        proposicoes = json.load(f)

    processos = [
        {
            "id": p["id"],
            "url": URL.format(p["id"])
        }
        for p in proposicoes
        if p.get("id")
    ]

    if not processos:
        print("Nenhuma proposição encontrada.")
        return

    urls = [p["url"] for p in processos]

    print(f"🚀 Coletando {len(urls)} proposições...")

    collector = AsyncCollector(
        max_concurrent=10,
        retries=5
    )

    raw_results = await collector.collect(urls)

    resultados = []

    for processo, res in zip(processos, raw_results):

        id_prop = processo["id"]

        nome_proposicao = None
        situacao = None
        nome_norma = None

        if isinstance(res, str):
            try:
                root = ET.fromstring(res)
                strip_namespace(root)

                nome_proposicao = find_text(root, "nomeProposicao")
                situacao = find_text(root, "Situacao")

                nome_norma = extrair_nome_norma(situacao)

            except Exception as e:
                print(f"Erro ao processar {id_prop}: {e}")
        if nome_norma:
            resultados.append({
                "id": id_prop,
                "nomeProposicao": nome_proposicao,
                "situacao": situacao,
                "nome_norma": nome_norma
            })

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            resultados,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(f"✅ Processadas: {len(resultados)}")
    print(f"💾 Salvo em: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())