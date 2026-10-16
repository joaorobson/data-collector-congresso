import asyncio
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

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

MAX_CONCURRENT = 15
BATCH_SIZE = 150


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


def normalizar_payload_camara(resposta_collector: Any) -> Dict[str, Any]:
    if not isinstance(resposta_collector, dict):
        return {"dados": []}

    corpo = (
        resposta_collector.get("resultado")
        if "resultado" in resposta_collector
        else resposta_collector
    )
    if not isinstance(corpo, dict):
        return {"dados": []}

    dados = corpo.get("dados")
    if isinstance(dados, dict):
        return {"dados": [dados]}
    if isinstance(dados, list):
        return {"dados": dados}

    return {"dados": []}


def salvar_progresso(caminho: Path, dados: Dict[str, Any]):
    """Salva estado atual em disco de forma segura."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


async def buscar_id_api_antiga(
    session: aiohttp.ClientSession, sigla: str, numero: str, ano: str
) -> Optional[str]:
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
    # PREPARAÇÃO E CHECAGEM DE CACHE
    # ==========================================================
    for urn, prop in proposicoes_origem.items():
        origens = prop.get("origem_final") or []
        casas = prop.get("casas") or []
        urls = prop.get("urls") or []

        registros_atuais = resultados.get(urn, [])
        novos_registros = []

        for idx, (origem, casa, url) in enumerate(zip(origens, casas, urls)):
            registro_existente = (
                registros_atuais[idx] if idx < len(registros_atuais) else None
            )

            if casa != "CD":
                total_outras_casas += 1
                novos_registros.append(
                    registro_existente
                    if registro_existente
                    else criar_registro(
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

            if not origem:
                novos_registros.append(
                    registro_existente
                    if registro_existente
                    else criar_registro(
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
            sigla, numero, ano = match.groups() if match else (None, None, None)

            # Se já está coletado em disco, mantém
            if not precisa_coletar(registro_existente):
                novos_registros.append(registro_existente)
                total_cd_mantidos += 1
                continue

            # Prioriza ID direto caso presente na URL
            id_proposicao = None
            if url:
                match_url = re.search(r"idProposicao=(\d+)", url)
                if match_url:
                    id_proposicao = match_url.group(1)

            if id_proposicao:
                url_busca = f"{BASE_URL}/{id_proposicao}"
            elif sigla and numero and ano:
                url_busca = (
                    f"{BASE_URL}?"
                    f"siglaTipo={sigla}&numero={numero}&ano={ano}&"
                    f"ordem=ASC&ordenarPor=id"
                )
            else:
                novos_registros.append(
                    registro_existente
                    if registro_existente
                    else criar_registro(
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
                    "tem_id_direto": id_proposicao is not None,
                }
            )

            novos_registros.append(
                registro_existente
                if registro_existente
                else criar_registro(
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
    # EXECUÇÃO EM LOTES (CHUNKS) COM SALVAMENTO PERIÓDICO
    # ==========================================================
    total_pendente = len(metadata_para_coleta)
    if total_pendente > 0:
        print(
            f"\n🚀 Total a coletar: {total_pendente} proposições "
            f"(em lotes de {BATCH_SIZE}, concorrência={MAX_CONCURRENT})..."
        )
        collector = AsyncCollector(max_concurrent=MAX_CONCURRENT, retries=3)

        for i in range(0, total_pendente, BATCH_SIZE):
            lote = metadata_para_coleta[i : i + BATCH_SIZE]
            lote_num = (i // BATCH_SIZE) + 1
            total_lotes = (total_pendente + BATCH_SIZE - 1) // BATCH_SIZE

            print(f"\n📦 Processando Lote [{lote_num}/{total_lotes}] ({len(lote)} itens)...")

            # --- ETAPA 1: Chamada inicial (detalhe se já tem ID, ou busca se não tem) ---
            urls_chamada = [m["url_busca"] for m in lote]
            respostas_chamada = await collector.collect(urls_chamada)

            pendentes_resolucao = []
            for meta, resp in zip(lote, respostas_chamada):
                urn = meta["urn"]
                idx = meta["index"]

                # Se já foi chamada direta com ID, salva o payload detalhado
                if meta["tem_id_direto"]:
                    resultados[urn][idx] = criar_registro(
                        urn=urn,
                        url=meta["url_busca"],
                        origem=meta["origem"],
                        casa=meta["casa"],
                        sigla=meta["sigla"],
                        numero=meta["numero"],
                        ano=meta["ano"],
                        resultado=normalizar_payload_camara(resp),
                    )
                else:
                    # Se era busca por filtros, extrai o id retornado
                    corpo = resp.get("resultado", {}) if isinstance(resp, dict) else {}
                    dados = corpo.get("dados") if isinstance(corpo, dict) else []
                    id_prop = str(dados[0].get("id")) if isinstance(dados, list) and dados else None
                    pendentes_resolucao.append((meta, id_prop))

            # --- ETAPA 2: Fallback legado e detalhamento apenas para os que não tinham ID direto ---
            if pendentes_resolucao:
                faltantes_soap = [
                    (meta, idx_p)
                    for idx_p, (meta, id_p) in enumerate(pendentes_resolucao)
                    if not id_p
                ]

                if faltantes_soap:
                    async with aiohttp.ClientSession() as session:
                        tasks = [
                            buscar_id_api_antiga(
                                session, m["sigla"], m["numero"], m["ano"]
                            )
                            for m, _ in faltantes_soap
                        ]
                        ids_soap = await tqdm.gather(
                            *tasks, desc="API Legada (SOAP)", leave=False
                        )
                        for (_, idx_p), id_rec in zip(faltantes_soap, ids_soap):
                            if id_rec:
                                pendentes_resolucao[idx_p] = (
                                    pendentes_resolucao[idx_p][0],
                                    str(id_rec),
                                )

                itens_para_detalhar = [
                    (meta, f"{BASE_URL}/{id_p}")
                    for meta, id_p in pendentes_resolucao
                    if id_p
                ]

                if itens_para_detalhar:
                    urls_det = [url for _, url in itens_para_detalhar]
                    respostas_det = await collector.collect(urls_det)

                    for (meta, url_det), resp_det in zip(itens_para_detalhar, respostas_det):
                        urn = meta["urn"]
                        idx = meta["index"]
                        resultados[urn][idx] = criar_registro(
                            urn=urn,
                            url=url_det,
                            origem=meta["origem"],
                            casa=meta["casa"],
                            sigla=meta["sigla"],
                            numero=meta["numero"],
                            ano=meta["ano"],
                            resultado=normalizar_payload_camara(resp_det),
                        )

            # Checkpoint: Salva após cada lote finalizado
            salvar_progresso(output_path, resultados)
            print(f"💾 Progresso salvo em disco após o lote {lote_num}.")
            await asyncio.sleep(1.0)

    else:
        print("\n✅ Todas as proposições da Câmara já estavam completas em cache.")

    elapsed = time.time() - start_time
    print("\n🏁 Coleta finalizada com sucesso!")
    print(f"📊 URNs processadas: {len(resultados)}")
    print(f"🏛️ Outras casas mantidas: {total_outras_casas}")
    print(f"💾 Registros mantidos em cache: {total_cd_mantidos}")
    print(f"🌐 Proposições consultadas nesta execução: {total_pendente}")
    print(f"⏱️ Tempo total: {elapsed:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())