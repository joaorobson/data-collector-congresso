import asyncio
import json
import time
from pathlib import Path
from src.shared.async_collector import AsyncCollector

async def main():
    start_time = time.time()
    
    # Configurações de caminhos
    input_tipos = "data/senado/sigla_tipos_proposicoes.json"
    output_file = "data/senado/infos_proposicoes.json"
    base_url = "https://legis.senado.leg.br/dadosabertos/processo"
    
    # 2. Carregar siglas dos tipos
    if not Path(input_tipos).exists():
        print(f"❌ Arquivo não encontrado: {input_tipos}")
        return

    with open(input_tipos, "r", encoding="utf-8") as f:
        tipos_processos = json.load(f)

    anos = range(2000, 2025)
    
    # 3. Gerar URLs (Lógica por Anos)
    urls = []
    for tipo in tipos_processos:
        for ano in anos:
            url = (
                f"{base_url}?"
                f"siglaTipoDocumento={tipo}&"
                f"dataInicioApresentacao={ano}-01-01&"
                f"dataFimApresentacao={ano}-12-31"
            )
            urls.append(url)

    print(f"🚀 Iniciando coleta de {len(urls)} requisições...")
    print(f"📥 Formato detectado: Lista direta de objetos.")

    # 4. Executar coleta assíncrona
    collector = AsyncCollector(max_concurrent=10, retries=5)
    raw_results = await collector.collect(urls)

    # 5. Consolidação Direta
    # Como o retorno é [{}, {}], basta dar um extend na nossa lista principal
    collected_data = []
    
    for res in raw_results:
        if res and isinstance(res, list):
            collected_data.extend(res)
        elif res and isinstance(res, dict):
            # Fallback caso a API retorne um objeto único em vez de lista
            collected_data.append(res)

    # 6. Salvar o JSON integral
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(collected_data, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time
    print(f"\n✅ Processo concluído!")
    print(f"📊 Total de registros acumulados: {len(collected_data)}")
    print(f"💾 Salvo em: {output_file}")
    print(f"⏱️ Tempo total: {elapsed:.2f} segundos")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Coleta interrompida.")