import asyncio
import json
import os
import aiohttp

# Configurações de concorrência para o download dos PDFs
MAX_CONCURRENT_DOWNLOADS = 10
RETRIES = 3

async def baixar_pdf(session, url, caminho_destino, semaphore):
    """Realiza o download de um PDF individual de forma assíncrona."""
    async with semaphore:
        for tentativa in range(1, RETRIES + 1):
            try:
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        # Lê o conteúdo binário do PDF
                        conteudo = await response.read()
                        
                        # Grava o arquivo localmente
                        with open(caminho_destino, "wb") as f:
                            f.write(conteudo)
                        return True
                    else:
                        print(f"⚠️ Erro {response.status} ao baixar: {url} (Tentativa {tentativa}/{RETRIES})")
            except Exception as e:
                print(f"⚠️ Falha na conexão para {url}: {e} (Tentativa {tentativa}/{RETRIES})")
            
            await asyncio.sleep(1 * tentativa)  # Backoff simples antes de tentar de novo
        
        print(f"❌ Falha definitiva ao baixar: {url}")
        return False

async def main():
    input_path = "data/senado/metadados/info_proposicoes.json"
    output_dir = "data/senado/metadados/docs/proposicoes"

    if not os.path.exists(input_path):
        print(f"❌ Arquivo não encontrado: {input_path}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        try:
            proposicoes = json.load(f)
        except json.JSONDecodeError as e:
            print(f"❌ Erro ao ler o arquivo JSON: {e}")
            return

    downloads_agendados = []

    # Extrai as URLs dos documentos e mapeia para o local onde serão salvas
    for urn, props in proposicoes.items():
        if not urn or not isinstance(props, list):
            continue
            
        for prop in props:
            resultado = prop.get("resultado") or []

            for item in resultado:
                url_doc = item.get("urlDocumento")
                id_documento = item.get("id")
                
                if url_doc and id_documento:
                    # Define o nome do arquivo usando o 'id' do resultado
                    nome_arquivo = f"{id_documento}.pdf"
                    caminho_completo = os.path.join(output_dir, nome_arquivo)
                    
                    downloads_agendados.append({
                        "url": url_doc,
                        "caminho": caminho_completo,
                        "id": id_documento
                    })

    if not downloads_agendados:
        print("⚠️ Nenhum documento PDF encontrado para baixar.")
        return

    # Garante que a pasta de destino exista
    os.makedirs(output_dir, exist_ok=True)

    print(f"🚀 Iniciando o download de {len(downloads_agendados)} PDFs...")

    # Semáforo para limitar downloads simultâneos e evitar sobrecarregar o servidor do Senado
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
    
    async with aiohttp.ClientSession() as session:
        tarefas = []
        for download in downloads_agendados:
            tarefas.append(
                baixar_pdf(session, download["url"], download["caminho"], semaphore)
            )
        
        # Executa todas as tarefas concorrentemente
        resultados = await asyncio.gather(*tarefas)

    sucessos = sum(1 for r in resultados if r)
    
    print(f"\n✅ Download concluído!")
    print(f"📦 PDFs baixados com sucesso na pasta '{output_dir}': {sucessos}/{len(downloads_agendados)}")


if __name__ == "__main__":
    asyncio.run(main())