import asyncio
import json
from datetime import date, timedelta
from urllib.parse import urlparse, parse_qs
from src.shared.async_collector import AsyncCollector

URL_TEMPLATE = "https://dadosabertos.camara.leg.br/api/v2/proposicoes?siglaTipo={}&dataApresentacaoInicio={}&dataApresentacaoFim={}&pagina={}&itens=100"

# 1. Carregar tipos
with open("data/camara/sigla_tipos_filtradas.json", "r", encoding="utf-8") as f:
    TIPOS_PROCESSOS_CAMARA = json.load(f)
    SIGLAS_STRING = ",".join(TIPOS_PROCESSOS_CAMARA)

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

async def main():
    collector = AsyncCollector(max_concurrent=10)
    trimestres = quarter_ranges(end_date=date(2024, 12, 31))
    
    # Passo 1: Gerar as URLs apenas das "Páginas 1"
    urls_pagina_1 = [
        URL_TEMPLATE.format(SIGLAS_STRING, r[0], r[1], 1) 
        for r in trimestres
    ]
    
    print(f"🔍 Verificando paginação para {len(urls_pagina_1)} trimestres...")
    
    # Passo 2: Coletar os dados das páginas 1 (com links de paginação)
    # Aqui não usamos o extract_data que remove os links, 
    # então vamos garantir que o collector retorne o JSON completo ou ajustar a chamada
    resultados_p1 = await collector.collect(urls_pagina_1)
    
    all_urls = []
    
    # Passo 3: Processar os links para encontrar as páginas restantes
    for i, data in enumerate(resultados_p1):
        if not data:
            continue
            
        # Adiciona a página 1 que já foi validada
        all_urls.append(urls_pagina_1[i])
        
        # A API da Câmara retorna os links dentro de um envelope. 
        # Se o seu _extract_data já removeu o envelope, você precisará ajustar 
        # a classe AsyncCollector para não extrair nada se quiser os links aqui.
        links = data.get("links", []) if isinstance(data, dict) else []
        last_page_link = [link for link in links if link.get("rel") == "last"]
        
        if last_page_link:
            last_page_url = last_page_link[0].get("href")
            parsed_url = urlparse(last_page_url)
            query_params = parse_qs(parsed_url.query)
            last_page_num = int(query_params.get("pagina", [1])[0])
            
            # Pega as datas do intervalo atual para reconstruir as URLs das páginas 2 em diante
            data_ini, data_fim = trimestres[i]
            for page in range(2, last_page_num + 1):
                all_urls.append(URL_TEMPLATE.format(SIGLAS_STRING, data_ini, data_fim, page))

    print(f"✅ Total de URLs geradas: {len(all_urls)}")
    
    # Salvar a lista de URLs
    with open("data/camara/urls_proposicoes.json", "w", encoding="utf-8") as f:
        json.dump(all_urls, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(main())