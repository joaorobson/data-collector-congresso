import asyncio
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from src.shared.async_collector import AsyncCollector
from tqdm.asyncio import tqdm

INPUT_FILE = "data/normas/metadados/proposicoes_origem_normalizadas.json"
OUTPUT_FILE = "data/camara/metadados/proposicoes.json"

BASE_URL = "https://dadosabertos.camara.leg.br/api/v2/proposicoes"
OLD_BASE_URL = (
    "https://www.camara.leg.br/SitCamaraWS/Proposicoes.asmx/ObterProposicao"
)

PATTERN = re.compile(r"([A-Z]+)\s+(\d+A?)/(\d{4})")


def precisa_coletar(registro_existente: Optional[Dict[str, Any]]) -> bool:
    """Verifica se um registro já possui os dados detalhados da proposição."""
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
    if not dados or not isinstance(dados, list) or len(dados) == 0:
        return True

    primeiro_item = dados[0]
    # Possui dados completos se contiver statusProposicao ou urlInteiroTeor
    if isinstance(primeiro_item, dict) and (
        "statusProposicao" in primeiro_item or "urlInteiroTeor" in primeiro_item
    ):
        return False

    return True


def criar_registro(
    urn: str,
    url: str,
    origem: Optional[str],
    casa: Optional[str],
    sigla: Optional[str],
    numero: Optional[str],
    ano: Optional[str],
    resultado: Dict[str, Any],
) -> Dict[str, Any]:
    """Cria um registro padronizado no formato da base de dados."""
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


async def buscar_id_api_antiga(
    session: aiohttp.ClientSession, sigla: str, numero: str, ano: str
) -> Optional[str]:
    """Fallback: consulta a API SOAP/XML legada para recuperar o idProposicao numérico."""
    url = f"{OLD_BASE_URL}?tipo={sigla}&numero={numero}&ano={ano}"
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                return None

            xml = await resp.text()
            root = ET.fromstring(xml)
            id_prop = root.findtext("idProposicao")
            if id_prop:
                return id_prop.strip()
    except Exception as e:
        print(f"⚠️ Erro na API legada ({sigla} {numero}/{ano}): {e}")

    return None


async def main():
    start_time = time.time()

    input_path = Path(INPUT_FILE)
    output_path = Path(OUTPUT_FILE)

    if not input_path.exists():
        raise FileNotFoundError(f"❌ Arquivo de entrada não encontrado: {input_path}")

    with input_path.open("r", encoding="utf-8") as f:
        proposicoes_origem = json.load(f)

    resultados = {}
    if output_path.exists():
        print(f"📂 Carregando base existente em: {output_path}")
        with output_path.open("r", encoding="utf-8") as f:
            try:
                resultados = json.load(f)
            except json.JSONDecodeError:
                print("⚠️ JSON corrompido ou inválido. Reiniciando base.")
                resultados = {}

    metadata_para_coleta: List[Dict[str, Any]] = []
    total_outras_casas = 0
    total_cd_mantidos = 0

    # ==========================================================
    # PREPARAÇÃO DAS FILAS E VALIDAÇÃO DE CACHE
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

            # Demais casas legislativas e órgãos (SF, PR, CN)
            if casa != "CD":
                total_outras_casas += 1
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

            # Câmara dos Deputados (CD)
            if not origem:
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

            match = PATTERN.search(origem)
            if not match:
                sigla, numero, ano = None, None, None
            else:
                sigla, numero, ano = match.groups()

            # Cache hit: registro já possui payload detalhado
            if not precisa_coletar(registro_existente):
                novos_registros.append(registro_existente)
                total_cd_mantidos += 1
                continue

            if not sigla or not numero or not ano:
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

            url_busca = (
                f"{BASE_URL}?"
                f"siglaTipo={sigla}&numero={numero}&ano={ano}&"
                f"ordem=ASC&ordenarPor=id"
            )

            metadata_para_coleta.append(
                {
                    "urn": urn,
                    "index": idx,
                    "origem": origem,
                    "casa": casa,
                    "sigla": sigla,
                    "numero": numero,
                    "ano": ano,
                    "url_busca": url_busca,
                }
            )

            # Placeholder atualizado até a resposta da requisição
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

        resultados[urn] = novos_registros

    # ==========================================================
    # EXECUÇÃO DO PIPELINE EM 2 ETAPAS EM LOTE
    # ==========================================================
    if metadata_para_coleta:
        total_props = len(metadata_para_coleta)
        collector = AsyncCollector(max_concurrent=15, retries=3)

        # ------------------------------------------------------
        # ETAPA 1.1: Consulta em lote à API v2 para obter IDs
        # ------------------------------------------------------
        print(f"\n🚀 [Etapa 1.1] Buscando IDs de {total_props} proposições na API v2...")
        urls_busca = [m["url_busca"] for m in metadata_para_coleta]
        respostas_busca = await collector.collect(urls_busca)

        mapa_ids: Dict[int, str] = {}
        pendentes_legado: List[Tuple[int, Dict[str, Any]]] = []

        for i, (meta, resp) in enumerate(zip(metadata_para_coleta, respostas_busca)):
            id_encontrado = None
            if resp and isinstance(resp, dict):
                corpo = resp.get("resultado", {})
                dados = corpo.get("dados") if isinstance(corpo, dict) else []
                if isinstance(dados, list) and len(dados) > 0:
                    id_encontrado = str(dados[0].get("id"))

            if id_encontrado:
                mapa_ids[i] = id_encontrado
            else:
                pendentes_legado.append((i, meta))

        # ------------------------------------------------------
        # ETAPA 1.2: Fallback na API Legada para os IDs não encontrados
        # ------------------------------------------------------
        if pendentes_legado:
            print(f"\n🔎 [Etapa 1.2] Resolvendo {len(pendentes_legado)} proposições pendentes na API antiga...")
            async with aiohttp.ClientSession() as session:
                tasks_legado = [
                    buscar_id_api_antiga(
                        session, meta["sigla"], meta["numero"], meta["ano"]
                    )
                    for _, meta in pendentes_legado
                ]
                ids_legados = await tqdm.gather(
                    *tasks_legado, desc="API Legada (SOAP)"
                )

                for (i, meta), id_legado in zip(pendentes_legado, ids_legados):
                    if id_legado:
                        mapa_ids[i] = str(id_legado)
                    else:
                        print(f"❌ ID não localizado: {meta['origem']}")

        # ------------------------------------------------------
        # ETAPA 2: Consulta detalhada em lote por ID (/proposicoes/{id})
        # ------------------------------------------------------
        itens_para_detalhar = [
            (metadata_para_coleta[i], f"{BASE_URL}/{id_prop}")
            for i, id_prop in mapa_ids.items()
        ]

        if itens_para_detalhar:
            print(f"\n📥 [Etapa 2] Coletando detalhes completos de {len(itens_para_detalhar)} proposições...")
            urls_detalhe = [url for _, url in itens_para_detalhar]
            res_detalhes = await collector.collect(urls_detalhe)

            for (meta, url_detalhe), res in zip(itens_para_detalhar, res_detalhes):
                urn = meta["urn"]
                index = meta["index"]

                corpo = res.get("resultado") if isinstance(res, dict) else {}
                dados_detalhe = corpo.get("dados") if isinstance(corpo, dict) else None

                # Uniformiza objeto de detalhes sob lista [ {...} ]
                if isinstance(dados_detalhe, dict):
                    payload_dados = [dados_detalhe]
                elif isinstance(dados_detalhe, list):
                    payload_dados = dados_detalhe
                else:
                    payload_dados = []

                resultados[urn][index] = criar_registro(
                    urn=urn,
                    url=url_detalhe,
                    origem=meta["origem"],
                    casa=meta["casa"],
                    sigla=meta["sigla"],
                    numero=meta["numero"],
                    ano=meta["ano"],
                    resultado={"dados": payload_dados},
                )
    else:
        print("\n✅ Todas as proposições da Câmara já possuem dados detalhados atualizados.")

    # ==========================================================
    # PERSISTÊNCIA DOS DADOS
    # ==========================================================
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time
    print("\n✅ Coleta concluída com sucesso!")
    print(f"📊 URNs processadas: {len(resultados)}")
    print(f"🏛️ Registros de outras casas (SF/PR/CN): {total_outras_casas}")
    print(f"💾 Registros mantidos em cache: {total_cd_mantidos}")
    print(f"🌐 Proposições consultadas: {len(metadata_para_coleta)}")
    print(f"📁 Arquivo final: {output_path}")
    print(f"⏱️ Tempo total: {elapsed:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())