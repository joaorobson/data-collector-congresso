import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from tqdm import tqdm
from src.shared.async_collector import AsyncCollector

INPUT_FILE = "data/senado/metadados/proposicoes.json"
TIPOS_FILE = "data/senado/metadados/sigla_tipos_relatorios_e_pareceres.json"
OUTPUT_FILE = "data/senado/metadados/relatorios_e_pareceres.json"

URL_DOCUMENTOS = (
    "https://legis.senado.leg.br/dadosabertos/processo/documento"
    "?idProcesso={}&v=1"
)

# Configurações de estabilidade para o Senado
MAX_CONCURRENT = 4       # Concorrência reduzida para evitar erro de socket/firewall
BATCH_SIZE = 150         # Salva o arquivo em disco a cada lote


def salvar_progresso(caminho: Path, dados: Dict[str, Any]):
    """Salva estado atual em disco de forma segura."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def precisa_coletar(registro_existente: Optional[Dict[str, Any]]) -> bool:
    """Verifica se um registro já possui os documentos coletados com sucesso."""
    if not registro_existente:
        return True

    # Se houve falha na coleta (erro de request) ou status não é 200
    if registro_existente.get("status") != 200:
        return True
    
    if registro_existente.get("erro"):
        return True

    # Se ainda não existe a chave de resultado ou não for uma lista (mesmo que vazia), precisa coletar
    if "resultado" not in registro_existente or not isinstance(registro_existente["resultado"], list):
        return True

    return False


async def main():
    start_time = time.time()

    input_path = Path(INPUT_FILE)
    tipos_path = Path(TIPOS_FILE)
    output_path = Path(OUTPUT_FILE)

    if not input_path.exists():
        print(f"❌ Arquivo não encontrado: {input_path}")
        return

    if not tipos_path.exists():
        print(f"❌ Arquivo não encontrado: {tipos_path}")
        return

    with input_path.open("r", encoding="utf-8") as f:
        proposicoes = json.load(f)

    with tipos_path.open("r", encoding="utf-8") as f:
        siglas_permitidas = set(json.load(f))

    # -------------------------------------------------------
    # Carrega resultado anterior (execução incremental)
    # -------------------------------------------------------
    resultados = {}
    if output_path.exists():
        print(f"📂 Carregando base existente em: {output_path}")
        with output_path.open("r", encoding="utf-8") as f:
            try:
                resultados = json.load(f)
            except json.JSONDecodeError:
                print("⚠️ JSON corrompido ou inválido. Reiniciando base.")
                resultados = {}

    processos_para_coleta = []
    mantidos_em_cache = 0
    ids_vistos = set()

    # -------------------------------------------------------
    # Monta lista de processos pendentes
    # -------------------------------------------------------
    for urn, props in proposicoes.items():
        if not props:
            continue
            
        for prop in props:
            # Compatibilidade com o formato de resultado (pode ser dict ou list dependendo da extração)
            resultado_prop = prop.get("resultado") or []
            
            if isinstance(resultado_prop, list):
                dados = resultado_prop
            elif isinstance(resultado_prop, dict):
                dados = resultado_prop.get("dados") or []
                if isinstance(dados, dict):
                    dados = [dados]
            else:
                dados = []

            for item in dados:
                if not isinstance(item, dict):
                    continue

                # Extração segura do ID do processo
                id_processo = (
                    item.get("id") 
                    or item.get("codigoProcesso") 
                    or item.get("codigo") 
                    or item.get("codigoMateria")
                )
                
                if not id_processo:
                    continue
                
                id_processo = str(id_processo).strip()
                existente = resultados.get(id_processo)

                # Se já possui o resultado com sucesso -> não consulta novamente
                if not precisa_coletar(existente):
                    mantidos_em_cache += 1
                    continue

                # Evita enfileirar o mesmo ID de processo múltiplas vezes
                if id_processo not in ids_vistos:
                    ids_vistos.add(id_processo)
                    processos_para_coleta.append({
                        "id": id_processo,
                        "urn": urn,
                        "origem": prop.get("origem"),
                        "url": URL_DOCUMENTOS.format(id_processo),
                    })

    total_pendente = len(processos_para_coleta)

    if total_pendente == 0:
        print(f"✅ Tudo já processado. (Em cache: {mantidos_em_cache})")
        return

    # -------------------------------------------------------
    # EXECUÇÃO EM LOTES (CHUNKS) COM SALVAMENTO PERIÓDICO E TQDM
    # -------------------------------------------------------
    print(f"\n🚀 Total a coletar: {total_pendente} documentos (Lotes de {BATCH_SIZE}, Concorrência={MAX_CONCURRENT})...")
    
    collector = AsyncCollector(
        max_concurrent=MAX_CONCURRENT,
        retries=3,
    )

    # Barra de progresso com o tqdm
    with tqdm(total=total_pendente, desc="Coletando relatórios", unit="req") as pbar:
        for i in range(0, total_pendente, BATCH_SIZE):
            lote = processos_para_coleta[i : i + BATCH_SIZE]
            lote_num = (i // BATCH_SIZE) + 1

            urls_busca = [p["url"] for p in lote]
            respostas = await collector.collect(urls_busca)

            # Processa respostas do lote
            for processo, resposta in zip(lote, respostas):
                documentos = []
                status = resposta.get("status")
                erro = resposta.get("erro")

                if status == 200:
                    body = resposta.get("resultado")
                    if isinstance(body, list):
                        documentos = body
                    elif isinstance(body, dict):
                        documentos = [body]

                # Filtra os relatórios usando a lista de siglas permitidas
                documentos_filtrados = [
                    doc for doc in documentos
                    if doc.get("siglaTipo") in siglas_permitidas
                ]

                # Atualiza o dicionário principal usando o id da proposição como chave
                resultados[processo["id"]] = {
                    "urn": processo["urn"],
                    "origem": processo.get("origem"),
                    "status": status,
                    "erro": erro,
                    "resultado": documentos_filtrados,
                }

            # Checkpoint: Salva após cada lote finalizado
            salvar_progresso(output_path, resultados)
            
            # Usamos pbar.write() para não quebrar a linha da barra do tqdm
            pbar.write(f"💾 Lote {lote_num} finalizado. Progresso salvo em disco.")

            # Pausa para aliviar o socket e firewall do Senado
            await asyncio.sleep(1.5)
            
            pbar.update(len(lote))

    elapsed = time.time() - start_time
    print("\n🏁 Coleta finalizada com sucesso!")
    print(f"📊 Processos mapeados armazenados: {len(resultados)}")
    print(f"💾 Registros mantidos em cache: {mantidos_em_cache}")
    print(f"🌐 Processos consultados nesta execução: {total_pendente}")
    print(f"⏱️ Tempo total: {elapsed:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())