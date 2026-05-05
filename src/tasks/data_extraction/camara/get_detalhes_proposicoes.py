import asyncio
import json
import os
from src.shared.async_collector import AsyncCollector

async def main():
    input_path = 'data/camara/infos_proposicoes.json'
    output_path = 'data/camara/detalhes_proposicoes.json'

    # Carrega a lista de proposições básica
    if not os.path.exists(input_path):
        print(f"❌ Arquivo não encontrado: {input_path}")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        proposicoes_base = json.load(f)

    # Extrai apenas as URIs de detalhe
    # i['uri'] aponta para algo como ".../proposicoes/12345"
    urls = [i['uri'] for i in proposicoes_base if 'uri' in i]

    print(f"🚀 Coletando detalhes de {len(urls)} proposições...")

    # Aumentei um pouco a concorrência para detalhes (são requests individuais)
    collector = AsyncCollector(max_concurrent=10, retries=5)
    raw_results = await collector.collect(urls)

    # 2. Ajuste: Extrair apenas o conteúdo de 'dados' de cada resposta
    # Na API de detalhes, o campo 'dados' contém o objeto detalhado da proposição
    detalhes_finais = []
    for res in raw_results:
        if res and isinstance(res, dict) and "dados" in res:
            detalhes_finais.append(res["dados"])
        elif res is not None:
            detalhes_finais.append(res) # Fallback caso venha sem a chave 'dados'

    print(f"\n✅ Coleta concluída! Itens detalhados: {len(detalhes_finais)}")

    # 3. Salvar com encoding correto para não quebrar acentos das ementas
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(detalhes_finais, f, ensure_ascii=False, indent=2)

    print(f"💾 Resultados salvos em: {output_path}")

if __name__ == "__main__":
    asyncio.run(main())