import asyncio
import json
from pathlib import Path
import time

from src.shared.async_collector import AsyncCollector

async def collect_autores_consolidado():
    # Definição dos caminhos
    input_file = Path("data/camara/detalhes_proposicoes.json")
    output_file = Path("data/camara/autores_proposicoes.json")
    
    # Garante que a pasta de destino exista
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if not input_file.exists():
        print(f"❌ Arquivo de entrada não encontrado: {input_file}")
        return

    # 1. Carregar proposições base
    with open(input_file, 'r', encoding='utf-8') as f:
        proposicoes = json.load(f)

    # Mapear IDs e URLs
    tasks_info = [(p['id'], p['uriAutores']) for p in proposicoes if 'id' in p and 'uriAutores' in p]
    
    if not tasks_info:
        print("⚠️ Nenhuma URL de autores encontrada.")
        return

    urls = [info[1] for info in tasks_info]
    ids = [info[0] for info in tasks_info]

    print(f"🚀 Coletando autores de {len(urls)} proposições...")

    # 2. Coleta Assíncrona
    collector = AsyncCollector(max_concurrent=10, retries=5)
    start_time = time.time()
    raw_results = await collector.collect(urls)
    elapsed_time = time.time() - start_time

    print(f"\n✅ Coleta concluída em {elapsed_time:.2f}s. Consolidando dados...")

    # 3. Estruturar o JSON final
    autores = {}
    
    for i, res in enumerate(raw_results):
        proposicao_id = ids[i]
        
        # Se a resposta for válida e contiver a chave 'dados'
        if res and isinstance(res, dict) and "dados" in res:
            autores[proposicao_id] = {"autores": res["dados"]}
        else:
            # Caso falhe, podemos registrar que não houve retorno
            autores[proposicao_id] = {"autores": [], "erro": True}

    # 4. Salvar arquivo único
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(autores, f, ensure_ascii=False, indent=2)

    print(f"💾 Sucesso! Dados salvos em: {output_file}")
    print(f"📊 Total de registros: {len(autores)}")

if __name__ == "__main__":
    try:
        asyncio.run(collect_autores_consolidado())
    except KeyboardInterrupt:
        print("\n🛑 Interrompido.")