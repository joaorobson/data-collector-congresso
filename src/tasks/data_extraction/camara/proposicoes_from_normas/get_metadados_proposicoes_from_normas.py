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
    """
    Verifica se um registro salvo precisa ser coletado novamente.
    Retorna True se não existir, se status != 200, se houver erro ou se 'dados' vier vazio.
    """
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


def criar_registro(urn, url, origem, casa, sigla, numero, ano, resultado):
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
    """Verifica se o retorno do AsyncCollector veio sem dados válidos."""
    if not resposta_collector or not isinstance(resposta_collector, dict):
        return True

    if resposta_collector.get("status") != 200 or resposta_collector.get("erro"):
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
    """Consulta a API SOAP/XML antiga para obter o idProposicao numérico."""
    url = f"{OLD_BASE_URL}?tipo={sigla}&numero={numero}&ano={ano}"

    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None

            xml = await resp.text()
            root = ET.fromstring(xml)
            id_prop = root.findtext("idProposicao")

            if id_prop:
                return id_prop.strip()

    except Exception as e:
        print(f"⚠️ Erro ao consultar API antiga ({sigla} {numero}/{ano}): {e}")

    return None


async def processar_fallback(session, collector, meta, res):
    """
    Trata o fallback de forma assíncrona individual.
    Se a API v2 não retornou dados, tenta obter o ID via API antiga e faz nova chamada por ID na v2.
    """
    if not resposta_sem_dados(res):
        return meta, res

    sigla = meta["sigla"]
    numero = meta["numero"]
    ano = meta["ano"]

    if not sigla or not numero or not ano:
        return meta, res

    print(f"↪ Tentando API antiga em paralelo: {sigla} {numero}/{ano}")
    id_prop = await buscar_id_api_antiga(session, sigla, numero, ano)

    if not id_prop:
        return meta, res

    nova_url = f"{BASE_URL}/{id_prop}"
    print(f"   Encontrado ID {id_prop} para {sigla} {numero}/{ano}. Consultando v2 por ID...")

    novo_resultado = await collector.collect([nova_url])

    if novo_resultado:
        res_fallback = novo_resultado[0]

        # Normaliza resposta por ID (dict) para formato de lista
        if res_fallback.get("status") == 200 and isinstance(
            res_fallback.get("resultado"), dict
        ):
            dados_id = res_fallback["resultado"].get("dados")
            if isinstance(dados_id, dict):
                res_fallback["resultado"]["dados"] = [dados_id]

        meta_atualizado = meta.copy()
        meta_atualizado["url"] = nova_url
        return meta_atualizado, res_fallback

    return meta, res


async def main():
    start_time = time.time()

    input_path = Path(INPUT_FILE)
    output_path = Path(OUTPUT_FILE)

    if not input_path.exists():
        raise FileNotFoundError(f"❌ Arquivo de entrada não encontrado:\n{input_path}")

    with input_path.open("r", encoding="utf-8") as file:
        proposicoes_origem = json.load(file)

    resultados = {}

    if output_path.exists():
        print(f"📂 Carregando resultados existentes:\n{output_path}")
        with output_path.open("r", encoding="utf-8") as file:
            try:
                resultados = json.load(file)
            except json.JSONDecodeError:
                print("⚠️ O arquivo existente possui JSON inválido. Reiniciando base.")
                resultados = {}
    else:
        print("📂 Nenhum arquivo anterior encontrado. Iniciando nova coleta.")

    urls = []
    metadata = []

    total_outras_casas = 0
    total_cd_mantidos = 0
    total_cd_coletar = 0

    # ==========================================================
    # PREPARA AS CONSULTAS
    # ==========================================================

    for urn, prop in proposicoes_origem.items():
        origens = prop.get("origem_final") or []
        casas = prop.get("casas") or []

        registros_atuais = resultados.get(urn, [])
        novos_registros = []

        for idx, (origem, casa) in enumerate(zip(origens, casas)):
            registro_existente = (
                registros_atuais[idx] if idx < len(registros_atuais) else None
            )

            # --------------------------------------------------
            # OUTRAS CASAS (PR, SF, CN, etc.):
            # Não rodam a Regex nem consultam a API.
            # --------------------------------------------------
            if casa != "CD":
                total_outras_casas += 1
                if registro_existente:
                    novos_registros.append(registro_existente)
                else:
                    novos_registros.append(
                        criar_registro(
                            urn=urn,
                            url="",
                            origem=origem,
                            casa=casa,
                            sigla=None,
                            numero=None,
                            ano=None,
                            resultado={"dados": []},
                        )
                    )
                continue

            # --------------------------------------------------
            # PROPOSIÇÕES DA CÂMARA (CD):
            # Parse via Regex apenas se casa == "CD"
            # --------------------------------------------------
            if origem is None:
                print(f"⚠️ Origem nula para URN {urn} no índice {idx}. Ignorando.")
                continue

            match = PATTERN.search(origem)
            if not match:
                print(f"⚠️ Não foi possível interpretar origem CD: {origem}")
                sigla, numero, ano = None, None, None
            else:
                sigla, numero, ano = match.groups()

            # --------------------------------------------------
            # CHECA SE PRECISA REETETIR A REQUISIÇÃO (CD)
            # --------------------------------------------------
            if not precisa_coletar(registro_existente):
                novos_registros.append(registro_existente)
                total_cd_mantidos += 1
                continue

            if not sigla or not numero or not ano:
                print(f"⚠️ Impossível consultar API sem sigla/número/ano: {origem}")
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

            # --------------------------------------------------
            # MONTA URL DE CONSULTA NA CÂMARA
            # --------------------------------------------------
            total_cd_coletar += 1
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
    # EXECUÇÃO PARALELA DAS CONSULTAS E FALLBACKS
    # ==========================================================

    if urls:
        print(f"\n🚀 Coletando {len(urls)} proposições da Câmara (CD)...")

        collector = AsyncCollector(
            max_concurrent=15,
            retries=3,
        )

        raw_results = await collector.collect(urls)

        print("🔎 Verificando e aplicando fallback assíncrono paralelo (API antiga)...")

        async with aiohttp.ClientSession() as session:
            tasks = [
                processar_fallback(session, collector, meta, res)
                for meta, res in zip(metadata, raw_results)
            ]
            resultados_processados = await asyncio.gather(*tasks)

        # Atribuição dos resultados finais respeitando o índice original de cada URN
        for meta_atualizado, res_final in resultados_processados:
            urn = meta_atualizado["urn"]
            index = meta_atualizado["index"]

            corpo = res_final.get("resultado") if isinstance(res_final, dict) else {}
            payload_limpo = corpo if isinstance(corpo, dict) else {"dados": []}

            resultados[urn][index] = criar_registro(
                urn=meta_atualizado["urn"],
                url=meta_atualizado["url"],
                origem=meta_atualizado["origem"],
                casa=meta_atualizado["casa"],
                sigla=meta_atualizado["sigla"],
                numero=meta_atualizado["numero"],
                ano=meta_atualizado["ano"],
                resultado=payload_limpo,
            )
    else:
        print("\n✅ Nenhuma consulta à API da Câmara foi necessária nesta execução.")

    # ==========================================================
    # SALVA O ARQUIVO JSON
    # ==========================================================

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(resultados, file, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time

    print("\n✅ Processo concluído com sucesso!")
    print(f"📊 Total de URNs processadas: {len(resultados)}")
    print(f"🏛️ Registros de outras casas (PR/SF/CN) salvos sem requisição: {total_outras_casas}")
    print(f"💾 Registros de CD mantidos de execuções anteriores: {total_cd_mantidos}")
    print(f"🌐 Novas consultas de CD executadas: {total_cd_coletar}")
    print(f"💾 Arquivo final salvo em:\n{output_path}")
    print(f"⏱️ Tempo total: {elapsed:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())