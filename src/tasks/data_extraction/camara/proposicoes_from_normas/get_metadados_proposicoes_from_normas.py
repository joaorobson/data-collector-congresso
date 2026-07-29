import asyncio
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import aiohttp

from src.shared.async_collector import AsyncCollector

INPUT_FILE = "data/normas/metadados/proposicoes_origem_normalizadas.json"
OUTPUT_FILE = "data/camara/metadados/proposicoes.json"

BASE_URL = "https://dadosabertos.camara.leg.br/api/v2/proposicoes"
OLD_BASE_URL = (
    "https://www.camara.leg.br/SitCamaraWS/Proposicoes.asmx/ObterProposicao"
)

PATTERN = re.compile(r"([A-Z]+)\s+(\d+A?)/(\d{4})")


def precisa_coletar(registro_existente) -> bool:
    """Verifica se um registro salvo precisa ser coletado novamente."""
    if not registro_existente:
        return True

    res = registro_existente.get("resultado")

    if not res or not isinstance(res, dict):
        return True

    if res.get("status") and res.get("status") != 200:
        return True

    if res.get("erro"):
        return True

    dados = res.get("dados")
    if not dados:  # Avalia True para None, [], etc.
        return True

    return False


def criar_registro(
    urn,
    url,
    origem,
    casa,
    sigla,
    numero,
    ano,
    resultado,
):
    """Cria um registro no formato padrão da Câmara."""
    return {
        "urn": urn,
        "url": url,
        "origem": origem,
        "casa": casa,
        "sigla": sigla,
        "numero": numero,
        "ano": ano,
        "resultado": resultado,
    }


def resposta_sem_dados(resposta_collector) -> bool:
    """Verifica se o retorno do AsyncCollector veio sem dados de proposição."""
    if not resposta_collector or not isinstance(resposta_collector, dict):
        return True

    if resposta_collector.get("status") != 200 or resposta_collector.get(
        "erro"
    ):
        return True

    body = resposta_collector.get("resultado")
    if not body or not isinstance(body, dict):
        return True

    dados = body.get("dados")
    if not dados:
        return True

    if isinstance(dados, list) and len(dados) == 0:
        return True

    return False


async def buscar_id_api_antiga(session, sigla, numero, ano):
    """Consulta a API antiga para tentar obter o idProposicao numérico."""
    url = f"{OLD_BASE_URL}?tipo={sigla}&numero={numero}&ano={ano}"

    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None

            xml = await resp.text()
            root = ET.fromstring(xml)
            id_prop = root.findtext("idProposicao")

            if id_prop:
                return id_prop.strip()

    except Exception as e:
        print(f"Erro consultando API antiga: {url}")
        print(e)

    return None


async def main():
    start_time = time.time()

    input_path = Path(INPUT_FILE)
    output_path = Path(OUTPUT_FILE)

    # ==========================================================
    # LÊ O ARQUIVO DE ORIGEM
    # ==========================================================

    if not input_path.exists():
        raise FileNotFoundError(
            f"❌ Arquivo de entrada não encontrado:\n{input_path}"
        )

    with input_path.open("r", encoding="utf-8") as file:
        proposicoes_origem = json.load(file)

    # ==========================================================
    # LÊ OS RESULTADOS JÁ SALVOS
    # ==========================================================

    resultados = {}

    if output_path.exists():
        print(f"📂 Carregando resultados existentes:\n{output_path}")
        with output_path.open("r", encoding="utf-8") as file:
            try:
                resultados = json.load(file)
            except json.JSONDecodeError:
                print(
                    "⚠️ O arquivo existente possui JSON inválido. Será iniciado um novo arquivo."
                )
                resultados = {}
    else:
        print("📂 Nenhum arquivo anterior encontrado. Iniciando nova coleta.")

    # ==========================================================
    # PREPARA AS CONSULTAS
    # ==========================================================

    urls = []
    metadata = []

    total_mantidos = 0
    total_sf_cn_ignorados = 0

    for urn, prop in proposicoes_origem.items():
        origens = prop.get("origem_final") or []
        casas = prop.get("casas") or [None] * len(origens)

        registros_atuais = resultados.get(urn, [])
        novos_registros = []

        for idx, (origem, casa) in enumerate(zip(origens, casas)):
            match = PATTERN.search(origem)

            if not match:
                print(f"⚠️ Não foi possível interpretar: {origem}")
                continue

            sigla, numero, ano = match.groups()

            # ==================================================
            # NÃO CONSULTA PROPOSIÇÕES DO SENADO OU CONGRESSO
            # ==================================================
            if casa == "SF" or casa == "CN":
                total_sf_cn_ignorados += 1
                registro_existente = (
                    registros_atuais[idx]
                    if idx < len(registros_atuais)
                    else None
                )

                if registro_existente:
                    novos_registros.append(registro_existente)
                else:
                    novos_registros.append(
                        criar_registro(
                            urn=urn,
                            url="",
                            origem=origem,
                            casa=casa,
                            sigla=sigla,
                            numero=numero,
                            ano=ano,
                            resultado={"dados": []},
                        )
                    )
                continue

            # ==================================================
            # CONSULTA SOMENTE REGISTROS SEM RESULTADO
            # ==================================================
            registro_existente = (
                registros_atuais[idx] if idx < len(registros_atuais) else None
            )

            if not precisa_coletar(registro_existente):
                novos_registros.append(registro_existente)
                total_mantidos += 1
                continue

            # ==================================================
            # MONTA A URL PARA NOVA CONSULTA
            # ==================================================
            url = (
                f"{BASE_URL}?"
                f"siglaTipo={sigla}&"
                f"numero={numero}&"
                f"ano={ano}&"
                f"ordem=ASC&"
                f"ordenarPor=id"
            )

            urls.append(url)
            metadata.append(
                {
                    "urn": urn,
                    "index": idx,
                    "url": url,
                    "origem": origem,
                    "casa": casa,
                    "sigla": sigla,
                    "numero": numero,
                    "ano": ano,
                }
            )

            novos_registros.append(
                criar_registro(
                    urn=urn,
                    url=url,
                    origem=origem,
                    casa=casa,
                    sigla=sigla,
                    numero=numero,
                    ano=ano,
                    resultado={"dados": []},
                )
            )

        resultados[urn] = novos_registros

    # ==========================================================
    # EXECUTA AS NOVAS CONSULTAS E TRATA FALLBACK DA CÂMARA
    # ==========================================================

    if urls:
        print(f"\n🚀 Coletando {len(urls)} proposições da Câmara...")

        collector = AsyncCollector(
            max_concurrent=15,
            retries=3,
        )

        raw_results = await collector.collect(urls)

        print("🔎 Verificando e aplicando fallback na API antiga para resultados vazios...")

        async with aiohttp.ClientSession() as session:
            for i, (meta, res) in enumerate(zip(metadata, raw_results)):
                if not resposta_sem_dados(res):
                    continue

                print(
                    f"↪ Tentando API antiga: {meta['sigla']} {meta['numero']}/{meta['ano']}"
                )

                id_prop = await buscar_id_api_antiga(
                    session,
                    meta["sigla"],
                    meta["numero"],
                    meta["ano"],
                )

                if not id_prop:
                    continue

                nova_url = f"{BASE_URL}/{id_prop}"
                print(f"   Encontrado ID {id_prop}. Consultando API v2 por ID...")

                novo_resultado = await collector.collect([nova_url])

                if novo_resultado:
                    res_fallback = novo_resultado[0]

                    # Ajusta payload retornado por ID para manter o padrão de lista
                    if (
                        res_fallback.get("status") == 200
                        and isinstance(res_fallback.get("resultado"), dict)
                    ):
                        dados_id = res_fallback["resultado"].get("dados")
                        if isinstance(dados_id, dict):
                            res_fallback["resultado"]["dados"] = [dados_id]

                    raw_results[i] = res_fallback
                    meta["url"] = nova_url

        # ======================================================
        # INSERE AS RESPOSTAS NAS POSIÇÕES CORRETAS (SEM ANINHAMENTO DUPLO)
        # ======================================================
        for meta, res in zip(metadata, raw_results):
            urn = meta["urn"]
            index = meta["index"]

            corpo = res.get("resultado") if isinstance(res, dict) else {}
            payload_limpo = corpo if isinstance(corpo, dict) else {"dados": []}

            resultados[urn][index] = criar_registro(
                urn=urn,
                url=meta["url"],
                origem=meta["origem"],
                casa=meta["casa"],
                sigla=meta["sigla"],
                numero=meta["numero"],
                ano=meta["ano"],
                resultado=payload_limpo,
            )
    else:
        print("\n✅ Nenhuma coleta necessária.")

    # ==========================================================
    # SALVA O ARQUIVO
    # ==========================================================

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(resultados, file, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time

    print("\n✅ Processo concluído!")
    print(f"📊 Total de URNs: {len(resultados)}")
    print(f"🏛️ Registros de SF/CN ignorados: {total_sf_cn_ignorados}")
    print(f"💾 Resultados existentes mantidos: {total_mantidos}")
    print(f"🌐 Novas consultas realizadas: {len(urls)}")
    print(f"💾 Arquivo salvo em:\n{output_path}")
    print(f"⏱️ Tempo total: {elapsed:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())