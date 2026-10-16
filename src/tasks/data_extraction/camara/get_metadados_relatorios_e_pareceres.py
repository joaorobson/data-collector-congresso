import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from tqdm import tqdm
from src.shared.async_collector import AsyncCollector

INPUT_FILE = "data/camara/metadados/proposicoes.json"
TIPOS_FILE = "data/camara/metadados/sigla_tipos_relatorios_e_pareceres.json"
OUTPUT_FILE = "data/camara/metadados/relatorios_e_pareceres.json"

URL_RELACIONADAS = (
    "https://dadosabertos.camara.leg.br/api/v2/proposicoes/{}/relacionadas"
)

# Configurações de estabilidade para a API da Câmara
MAX_CONCURRENT = 10      # Câmara geralmente suporta bem 10 conexões
BATCH_SIZE = 150         # Salva o arquivo em disco a cada lote


def salvar_progresso(caminho: Path, dados: Dict[str, Any]):
    """Salva estado atual em disco de forma segura."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def precisa_coletar_relacionadas(registro_existente: Optional[Dict[str, Any]]) -> bool:
    """Verifica se a proposição já teve suas relacionadas coletadas com sucesso."""
    if not registro_existente:
        return True

    if registro_existente.get("status") != 200:
        return True
    
    if registro_existente.get("erro"):
        return True

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

    collector = AsyncCollector(
        max_concurrent=MAX_CONCURRENT,
        retries=5,
    )

    # =======================================================
    # ETAPA 1: BUSCA DE RELACIONADAS
    # =======================================================
    processos_pendentes = []
    mantidos_em_cache = 0

    for urn, props in proposicoes.items():
        for prop in props:
            resultado = prop.get("resultado") or {}
            if not isinstance(resultado, dict):
                continue

            dados = resultado.get("dados", [])
            for item in dados:
                id_processo = str(item.get("id"))
                if not id_processo:
                    continue

                existente = resultados.get(id_processo)

                # Já possui resultado da etapa 1 com sucesso
                if not precisa_coletar_relacionadas(existente):
                    mantidos_em_cache += 1
                    continue

                processos_pendentes.append({
                    "id": id_processo,
                    "urn": urn,
                    "origem": prop.get("origem"),
                    "url": URL_RELACIONADAS.format(id_processo),
                })

    total_pendente = len(processos_pendentes)
    print(f"\n📋 Proposições em cache (Etapa 1): {mantidos_em_cache}")

    if total_pendente > 0:
        print(f"🚀 Iniciando Etapa 1: {total_pendente} consultas de relatórios (Lotes de {BATCH_SIZE})...")
        
        with tqdm(total=total_pendente, desc="Etapa 1 (Relacionadas)", unit="req") as pbar:
            for i in range(0, total_pendente, BATCH_SIZE):
                lote = processos_pendentes[i : i + BATCH_SIZE]
                lote_num = (i // BATCH_SIZE) + 1

                urls_busca = [p["url"] for p in lote]
                respostas = await collector.collect(urls_busca)

                for processo, resposta in zip(lote, respostas):
                    relacionadas = []
                    status = resposta.get("status")
                    erro = resposta.get("erro")

                    if status == 200:
                        body = resposta.get("resultado")
                        if isinstance(body, dict):
                            dados_relacionadas = body.get("dados", [])
                            # Filtra as siglas
                            for r in dados_relacionadas:
                                if r.get("siglaTipo") in siglas_permitidas:
                                    relacionadas.append(r)

                    resultados[processo["id"]] = {
                        "urn": processo["urn"],
                        "origem": processo["origem"],
                        "status": status,
                        "erro": erro,
                        "resultado": relacionadas,
                    }

                salvar_progresso(output_path, resultados)
                pbar.write(f"💾 Etapa 1 - Lote {lote_num} finalizado e salvo.")
                await asyncio.sleep(1.0)
                pbar.update(len(lote))
    else:
        print("✅ Etapa 1: Todas as proposições já tiveram relatórios e pareceres buscados.")

    # =======================================================
    # ETAPA 2: BUSCA DE INTEIRO TEOR (DETALHES)
    # =======================================================
    
    # Criamos um mapeamento de referência para modificar o dicionário 'resultados' diretamente na memória
    uris_para_baixar = []
    relatorios_refs = {}  # uri -> lista de referências de dicionários de relatórios

    for id_proc, info in resultados.items():
        for emenda in info.get("resultado", []):
            if "urlInteiroTeor" not in emenda and emenda.get("uri"):
                uri = emenda["uri"]
                if uri not in relatorios_refs:
                    relatorios_refs[uri] = []
                    uris_para_baixar.append(uri)
                # Adiciona a referência do dict real para atualizar in-place depois
                relatorios_refs[uri].append(emenda)

    total_uris = len(uris_para_baixar)

    if total_uris > 0:
        print(f"\n🔍 Iniciando Etapa 2: {total_uris} relatórios pendentes de 'urlInteiroTeor'...")
        
        with tqdm(total=total_uris, desc="Etapa 2 (Inteiro Teor)", unit="req") as pbar:
            for i in range(0, total_uris, BATCH_SIZE):
                lote_uris = uris_para_baixar[i : i + BATCH_SIZE]
                lote_num = (i // BATCH_SIZE) + 1

                respostas_detalhes = await collector.collect(lote_uris)

                for uri, resp in zip(lote_uris, respostas_detalhes):
                    if resp.get("status") == 200 and isinstance(resp.get("resultado"), dict):
                        dados_detalhe = resp["resultado"].get("dados", {})
                        # Mesmo que seja None, salva para marcar que já tentamos buscar
                        url_teor = dados_detalhe.get("urlInteiroTeor")
                        
                        # Atualiza todos os relatórios (referências de dicionário) que apontam pra esta URI
                        for emenda_dict in relatorios_refs[uri]:
                            emenda_dict["urlInteiroTeor"] = url_teor

                # Salva o arquivo principal contendo agora os relatórios com urlInteiroTeor atualizado
                salvar_progresso(output_path, resultados)
                pbar.write(f"💾 Etapa 2 - Lote {lote_num} finalizado e salvo.")
                await asyncio.sleep(1.0)
                pbar.update(len(lote_uris))
    else:
        print("\n✅ Etapa 2: Nenhum relatório pendente de URL de Inteiro Teor.")


    elapsed = time.time() - start_time
    print("\n🏁 Processo da Câmara concluído com sucesso!")
    print(f"📦 Total de proposições rastreadas no arquivo: {len(resultados)}")
    print(f"⏱️ Tempo total: {elapsed:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())