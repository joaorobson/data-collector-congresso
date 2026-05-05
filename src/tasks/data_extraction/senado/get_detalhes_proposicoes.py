import asyncio
import json
import os
from src.shared.async_collector import AsyncCollector

async def main():
    input_path = 'data/senado/infos_proposicoes.json'
    output_path = 'data/senado/detalhes_proposicoes.json'

    # 1. Carrega a lista de proposições básica
    if not os.path.exists(input_path):
        print(f"❌ Arquivo não encontrado: {input_path}")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        proposicoes_base = json.load(f)

    # 2. Extrai os IDs e monta as URLs para o endpoint de processo
    # Usamos o 'id' para preencher o ID na URL
    base_url = "https://legis.senado.leg.br/dadosabertos/processo/{}?v=1"
    
    # Filtramos itens que possuem 'id'
    urls = [
        base_url.format(i['id']) 
        for i in proposicoes_base if 'id' in i
    ]

    if not urls:
        print("⚠️ Nenhuma URL gerada. Verifique se o campo 'id' existe no JSON de entrada.")
        return

    print(f"🚀 Coletando detalhes de {len(urls)} processos legislativos...")

    # 3. Executa a coleta assíncrona
    # Headers necessários para garantir o retorno em JSON
    headers = {'accept': 'application/json'}
    collector = AsyncCollector(max_concurrent=10, retries=5)
    
    # Nota: Assumindo que seu AsyncCollector aceita passar headers ou que já os trata internamente
    raw_results = await collector.collect(urls)

    # 4. Ajuste no parsing dos resultados
    # A estrutura comum do Senado para esse endpoint costuma vir dentro de "Processo"
    detalhes_finais = []
    for res in raw_results:
        if res and isinstance(res, dict):
            # Tenta pegar a chave raiz do retorno da API (geralmente 'Processo')
            # Se não houver, salva o objeto inteiro
            conteudo = res.get("Processo", res)
            detalhes_finais.append(conteudo)

    print(f"\n✅ Coleta concluída! Itens processados: {len(detalhes_finais)}")

    # 5. Salvar com encoding UTF-8
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(detalhes_finais, f, ensure_ascii=False, indent=2)

    print(f"💾 Resultados salvos em: {output_path}")

if __name__ == "__main__":
    asyncio.run(main())