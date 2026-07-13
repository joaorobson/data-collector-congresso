import json
from src.shared.async_collector import AsyncCollector
import asyncio


async def main():
    with open("data/normas/metadados//metadados/urls_projetos_resolucao_cd.json", "r") as f:
        urls = json.load(f)

    print(f"Iniciando coleta de {len(urls)} páginas...")

    collector = AsyncCollector(max_concurrent=10, retries=3)
    results = await collector.collect(urls)

    # ACHATAMENTO: Extrai apenas os itens da chave 'dados' de cada página
    proposicoes_final = []
    for pagina in results:
        if pagina and "dados" in pagina:
            proposicoes_final.extend(pagina["dados"])

    print(f"\n✅ Total de proposições coletadas: {len(proposicoes_final)}")
    
    # Salva apenas a lista de proposições (mais limpo)
    with open("data/normas/metadados//metadados/infos_projetos_resolucao_cd.json", "w", encoding="utf-8") as f:
        json.dump(proposicoes_final, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
