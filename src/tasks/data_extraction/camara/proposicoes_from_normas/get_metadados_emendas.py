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

    processos_pendentes = []

    # -------------------------------------------------------
    # 1. Monta lista de proposições pendentes da 1ª Etapa
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

                # Já possui resultado da etapa 1 -> não consulta novamente a lista de relacionadas
                if existente and "resultado" in existente:
                    continue

                processos_pendentes.append(
                    {
                        "id": id_processo,
                        "urn": urn,
                        "origem": prop["origem"],
                        "url": URL_RELACIONADAS.format(id_processo),
                    }
                )

    print(f"📋 Proposições pendentes de consulta inicial: {len(processos_pendentes)}")

    collector = AsyncCollector(
        max_concurrent=10,
        retries=5,
    )

    # Coleta 1ª Etapa (Apenas pendentes)
    if processos_pendentes:
        respostas = await collector.collect([p["url"] for p in processos_pendentes])

        for processo, resposta in zip(processos_pendentes, respostas):
            relacionadas = []

            if resposta["status"] == 200:
                body = resposta["resultado"]

                if isinstance(body, dict):
                    dados = body.get("dados", [])

                    for r in dados:
                        if r.get("siglaTipo") in siglas_permitidas:
                            relacionadas.append(r)

            resultados[processo["id"]] = {
                "urn": processo["urn"],
                "origem": processo["origem"],
                "status": resposta["status"],
                "erro": resposta["erro"],
                "resultado": relacionadas,
            }

    # -------------------------------------------------------
    # 2. Identifica emendas pendentes de 'urlInteiroTeor'
    # -------------------------------------------------------
    # Varre TODOS os resultados (antigos e novos) procurando emendas sem urlInteiroTeor
    uris_para_baixar = set()

    for id_proc, info in resultados.items():
        for emenda in info.get("resultado", []):
            # Se ainda não tem o campo ou se veio nulo/vazio, adiciona para baixar
            if "urlInteiroTeor" not in emenda and emenda.get("uri"):
                uris_para_baixar.add(emenda["uri"])

    print(f"🔍 Emendas pendentes de 'urlInteiroTeor': {len(uris_para_baixar)}")

    if uris_para_baixar:
        uris_lista = list(uris_para_baixar)
        respostas_detalhes = await collector.collect(uris_lista)

        # Mapeia URI -> urlInteiroTeor
        mapa_inteiro_teor = {}
        for uri, resp in zip(uris_lista, respostas_detalhes):
            if resp["status"] == 200 and isinstance(resp["resultado"], dict):
                dados_detalhe = resp["resultado"].get("dados", {})
                mapa_inteiro_teor[uri] = dados_detalhe.get("urlInteiroTeor")

        # Atualiza o arquivo em memória com as novas URLs encontradas
        for id_proc, info in resultados.items():
            for emenda in info.get("resultado", []):
                uri_emenda = emenda.get("uri")
                if uri_emenda in mapa_inteiro_teor:
                    emenda["urlInteiroTeor"] = mapa_inteiro_teor[uri_emenda]

    # -------------------------------------------------------
    # Salva resultado final consolidado
    # -------------------------------------------------------
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            resultados,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("\n✅ Processo concluído com sucesso!")
    print(f"📦 Total de proposições no arquivo: {len(resultados)}")
    print(f"💾 Arquivo atualizado em: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())