import asyncio
import json
import os
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import aiohttp
from tqdm.asyncio import tqdm

from src.shared.async_collector import AsyncCollector

URL_TEMPLATE = "https://dadosabertos.camara.leg.br/api/v2/proposicoes?siglaTipo={}&dataApresentacaoInicio={}&dataApresentacaoFim={}&pagina={}&itens=100"
XML_URL_TEMPLATE = "https://www.camara.leg.br/SitCamaraWS/Proposicoes.asmx/ObterProposicaoPorID?IdProp={}"
OUTPUT_PATH = "data/normas/metadados/projetos_resolucao_cd_transf_norma.json"


def quarter_ranges(start_year=2000, start_month=1, end_date=None):
    if end_date is None:
        end_date = date.today()
    ranges = []
    start = date(start_year, start_month, 1)
    while start <= end_date:
        end_month = start.month + 2
        if end_month == 12:
            end = date(start.year, 12, 31)
        else:
            next_month_first = date(start.year, end_month + 1, 1)
            end = next_month_first - timedelta(days=1)
        if end > end_date:
            end = end_date
        ranges.append((start.isoformat(), end.isoformat()))
        next_month = end_month + 1
        next_year = start.year + (next_month - 1) // 12
        next_month = (next_month - 1) % 12 + 1
        start = date(next_year, next_month, 1)
    return ranges


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
    prefixo = "Tranformada no(a)"
    if situacao and situacao.startswith(prefixo):
        return situacao.replace(prefixo, "").strip()
    return None


async def fetch_xml_safe(session, sem, url, retries=5):
    """Coleta o XML legado com controle de concorrência e sem cabeçalhos conflitantes."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "*/*"
    }
    
    for attempt in range(retries):
        async with sem:
            try:
                await asyncio.sleep(0.15)  # Espaçamento leve entre chamadas
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status == 200:
                        text = await response.text()
                        return text
                    elif response.status == 429:
                        wait = 2 ** attempt
                        await asyncio.sleep(wait)
                        continue
            except Exception:
                await asyncio.sleep(1 + attempt)
    return None


async def coletar_todos_xmls(ids, max_concurrent=3):
    sem = asyncio.Semaphore(max_concurrent)
    connector = aiohttp.TCPConnector(limit=max_concurrent + 2)
    
    results = []
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            fetch_xml_safe(session, sem, XML_URL_TEMPLATE.format(prop_id))
            for prop_id in ids
        ]
        # Barra de progresso atualizando item a item
        for f in tqdm.as_completed(tasks, desc="Coletando XMLs SitCamaraWS"):
            res = await f
            results.append(res)
            
    return results


async def main():
    collector_api_v2 = AsyncCollector(max_concurrent=10, retries=5)
    trimestres = quarter_ranges(end_date=date(2025, 12, 31))

    # =========================================================================
    # ETAPA 1: Mapear todas as URLs de paginação da API REST
    # =========================================================================
    urls_pagina_1 = [
        URL_TEMPLATE.format("PRC", r[0], r[1], 1)
        for r in trimestres
    ]
    print(f"🔍 [1/3] Verificando paginação para {len(urls_pagina_1)} trimestres...")
    respostas_p1 = await collector_api_v2.collect(urls_pagina_1)

    all_urls = []
    for i, item_res in enumerate(respostas_p1):
        if not item_res or item_res.get("status") != 200:
            continue

        data = item_res.get("resultado")
        if not isinstance(data, dict):
            continue

        all_urls.append(urls_pagina_1[i])
        links = data.get("links", [])
        last_page_link = [link for link in links if link.get("rel") == "last"]

        if last_page_link:
            last_page_url = last_page_link[0].get("href")
            query_params = parse_qs(urlparse(last_page_url).query)
            last_page_num = int(query_params.get("pagina", [1])[0])

            data_ini, data_fim = trimestres[i]
            for page in range(2, last_page_num + 1):
                all_urls.append(URL_TEMPLATE.format("PRC", data_ini, data_fim, page))

    print(f"✅ Total de páginas identificadas: {len(all_urls)}")

    # =========================================================================
    # ETAPA 2: Coletar metadados e extrair os IDs
    # =========================================================================
    print(f"🚀 [2/3] Coletando conteúdo de {len(all_urls)} páginas...")
    respostas_paginas = await collector_api_v2.collect(all_urls)

    ids_proposicoes = []
    vistos = set()

    for item_res in respostas_paginas:
        if not item_res or item_res.get("status") != 200:
            continue

        pagina = item_res.get("resultado")
        if isinstance(pagina, dict) and "dados" in pagina:
            for item in pagina["dados"]:
                prop_id = item.get("id")
                if prop_id and prop_id not in vistos:
                    vistos.add(prop_id)
                    ids_proposicoes.append(prop_id)

    print(f"✅ Total de proposições únicas encontradas: {len(ids_proposicoes)}")

    if not ids_proposicoes:
        print("❌ Nenhuma proposição encontrada.")
        return

    # =========================================================================
    # ETAPA 3: Coletar XML detalhado no SitCamaraWS (Sessão dedicada com as_completed)
    # =========================================================================
    print(f"🚀 [3/3] Consultando detalhes XML de {len(ids_proposicoes)} proposições...")
    
    # Execução controlada via TCPConnector dedicado
    sem = asyncio.Semaphore(3)
    connector = aiohttp.TCPConnector(limit=5)
    resultados_finais = []

    async with aiohttp.ClientSession(connector=connector) as session:
        async def processar_proposicao(prop_id):
            url = XML_URL_TEMPLATE.format(prop_id)
            conteudo_xml = await fetch_xml_safe(session, sem, url, retries=5)
            if not conteudo_xml:
                return None
            try:
                root = ET.fromstring(conteudo_xml)
                strip_namespace(root)
                nome_proposicao = find_text(root, "nomeProposicao")
                situacao = find_text(root, "Situacao")
                nome_norma = extrair_nome_norma(situacao)

                if nome_norma:
                    return {
                        "id": prop_id,
                        "nomeProposicao": nome_proposicao,
                        "situacao": situacao,
                        "nome_norma": nome_norma
                    }
            except Exception:
                pass
            return None

        tasks = [processar_proposicao(pid) for pid in ids_proposicoes]
        for f in tqdm.as_completed(tasks, desc="Processando XMLs"):
            res = await f
            if res:
                resultados_finais.append(res)

    # =========================================================================
    # Salvar resultado final consolidado
    # =========================================================================
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(resultados_finais, f, ensure_ascii=False, indent=2)

    print(f"🎉 Finalizado com sucesso! {len(resultados_finais)} normas transformadas encontradas.")
    print(f"💾 Arquivo gerado em: {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())