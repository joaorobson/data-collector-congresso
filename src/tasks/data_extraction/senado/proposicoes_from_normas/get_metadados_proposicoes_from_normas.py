import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.shared.async_collector import AsyncCollector

INPUT_FILE = "data/normas/metadados/proposicoes_origem_normalizadas.json"
OUTPUT_FILE = "data/senado/metadados/proposicoes.json"

BASE_URL = "https://legis.senado.leg.br/dadosabertos/processo"
PATTERN = re.compile(r"([A-Z]+)\s+(\d+A?)/(\d{4})")

# Configurações de estabilidade para o Senado
MAX_CONCURRENT = 4       # Reduzido de 10 para 4 para evitar erro de socket/firewall
BATCH_SIZE = 150         # Salva o arquivo em disco a cada 150 itens


def precisa_coletar(registro_existente: Optional[Dict[str, Any]]) -> bool:
    """Verifica se um registro já possui os dados analíticos detalhados do processo."""
    if not registro_existente:
        return True

    res = registro_existente.get("resultado")
    if not res or not isinstance(res, dict):
        return True

    if res.get("status") and res.get("status") != 200:
        return True

    if res.get("erro"):
        return True

    dados = res.get("dados")
    if not dados or not isinstance(dados, list) or len(dados) == 0:
        return True

    url = registro_existente.get("url", "")
    if not re.search(r"/processo/\d+", url):
        return True

    return False


def criar_registro(
    urn: str,
    url: str,
    origem: Optional[str],
    casa: Optional[str],
    sigla: Optional[str],
    numero: Optional[str],
    ano: Optional[str],
    resultado: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "urn": urn,
        "url": url,
        "origem": origem,
        "casa": casa,
        "sigla": sigla,
        "numero": numero,
        "ano": ano,
        "resultado": resultado,
    }


def extrair_id_processo(resposta_collector: Any) -> Optional[str]:
    if not isinstance(resposta_collector, dict):
        return None

    corpo = resposta_collector.get("resultado")
    if not corpo:
        return None

    itens = []
    if isinstance(corpo, list):
        itens = corpo
    elif isinstance(corpo, dict):
        if "processo" in corpo:
            proc = corpo["processo"]
            itens = proc if isinstance(proc, list) else [proc]
        elif "dados" in corpo:
            d = corpo["dados"]
            itens = d if isinstance(d, list) else [d]
        elif "pesquisaBasicaMateria" in corpo:
            mat = corpo["pesquisaBasicaMateria"].get("materia", [])
            itens = mat if isinstance(mat, list) else [mat]
        else:
            itens = [corpo]

    for item in itens:
        if isinstance(item, dict):
            id_val = (
                item.get("id")
                or item.get("codigoProcesso")
                or item.get("codigo")
                or item.get("codigoMateria")
            )
            if id_val is not None:
                return str(id_val).strip()

    return None


def normalizar_payload_senado(resposta_collector: Any) -> Dict[str, Any]:
    if not isinstance(resposta_collector, dict):
        return {"dados": []}

    corpo = resposta_collector.get("resultado")
    if not corpo:
        return {"dados": []}

    if isinstance(corpo, list):
        return {"dados": corpo}

    if isinstance(corpo, dict):
        if "dados" in corpo:
            return corpo

        if "processo" in corpo:
            proc = corpo.get("processo")
            return {"dados": [proc] if isinstance(proc, dict) else proc}

        return {"dados": [corpo]}

    return {"dados": []}


def salvar_progresso(caminho: Path, dados: Dict[str, Any]):
    """Salva estado atual em disco de forma segura."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


async def main():
    start_time = time.time()

    input_path = Path(INPUT_FILE)
    output_path = Path(OUTPUT_FILE)

    if not input_path.exists():
        raise FileNotFoundError(f"❌ Arquivo de entrada não encontrado: {input_path}")

    with input_path.open("r", encoding="utf-8") as f:
        proposicoes_origem = json.load(f)

    resultados = {}
    if output_path.exists():
        print(f"📂 Carregando base existente em: {output_path}")
        with output_path.open("r", encoding="utf-8") as f:
            try:
                resultados = json.load(f)
            except json.JSONDecodeError:
                print("⚠️ JSON corrompido ou inválido. Reiniciando base.")
                resultados = {}

    metadata_para_coleta: List[Dict[str, Any]] = []
    total_outras_casas = 0
    total_sf_mantidos = 0

    # ==========================================================
    # PREPARAÇÃO E CHECAGEM DE CACHE
    # ==========================================================
    for urn, prop in proposicoes_origem.items():
        origens = prop.get("origem_final") or []
        casas = prop.get("casas") or []

        registros_atuais = resultados.get(urn, [])
        novos_registros = []

        for idx, (origem, casa) in enumerate(zip(origens, casas)):
            registro_existente = (
                registros_atuais[idx] if idx < len(registros_atuais) else None
            )

            if casa != "SF" and casa != "CN":
                total_outras_casas += 1
                novos_registros.append(
                    registro_existente
                    if registro_existente
                    else criar_registro(
                        urn=urn,
                        url="",
                        origem=origem,
                        casa=casa,
                        sigla=None,
                        numero=None,
                        ano=None,
                        resultado={"dados": []},
                    )
                )
                continue

            if not origem:
                if not origem:
                    novos_registros.append(
                        criar_registro(
                            urn=urn,
                            url="",
                            origem=origem,
                            casa=casa,
                            sigla=None,
                            numero=None,
                            ano=None,
                            resultado={"dados": []},
                        )
                    )
                    continue

            match = PATTERN.search(origem)
            if not match:
                sigla, numero, ano = None, None, None
            else:
                sigla, numero, ano = match.groups()

            # Se já está coletado em disco, mantém
            if not precisa_coletar(registro_existente):
                novos_registros.append(registro_existente)
                total_sf_mantidos += 1
                continue

            if not sigla or not numero or not ano:
                novos_registros.append(
                    criar_registro(
                        urn=urn,
                        url="",
                        origem=origem,
                        casa=casa,
                        sigla=sigla,
                        numero=numero,
                        ano=ano,
                        resultado={"dados": []},
                    )
                )
                continue

            url_busca = f"{BASE_URL}?sigla={sigla}&numero={numero}&ano={ano}&v=1"

            metadata_para_coleta.append(
                {
                    "urn": urn,
                    "index": idx,
                    "origem": origem,
                    "casa": casa,
                    "sigla": sigla,
                    "numero": numero,
                    "ano": ano,
                    "url_busca": url_busca,
                }
            )

            novos_registros.append(
                registro_existente
                if registro_existente
                else criar_registro(
                    urn=urn,
                    url="",
                    origem=origem,
                    casa=casa,
                    sigla=sigla,
                    numero=numero,
                    ano=ano,
                    resultado={"dados": []},
                )
            )

        resultados[urn] = novos_registros

    # ==========================================================
    # EXECUÇÃO EM LOTES (CHUNKS) COM SALVAMENTO PERIÓDICO
    # ==========================================================
    total_pendente = len(metadata_para_coleta)
    print(metadata_para_coleta)
    if total_pendente > 0:
        print(f"\n🚀 Total a coletar: {total_pendente} matérias (em lotes de {BATCH_SIZE}, concorrência={MAX_CONCURRENT})...")
        collector = AsyncCollector(max_concurrent=MAX_CONCURRENT, retries=3)

        for i in range(0, total_pendente, BATCH_SIZE):
            lote = metadata_para_coleta[i : i + BATCH_SIZE]
            lote_num = (i // BATCH_SIZE) + 1
            total_lotes = (total_pendente + BATCH_SIZE - 1) // BATCH_SIZE

            print(f"\n📦 Processando Lote [{lote_num}/{total_lotes}] ({len(lote)} itens)...")

            # --- ETAPA 1: Busca de IDs do lote ---
            urls_busca = [m["url_busca"] for m in lote]
            respostas_busca = await collector.collect(urls_busca)

            itens_para_detalhar = []
            for meta, resp in zip(lote, respostas_busca):
                id_encontrado = extrair_id_processo(resp)
                if id_encontrado:
                    url_detalhe = f"{BASE_URL}/{id_encontrado}?v=1"
                    itens_para_detalhar.append((meta, url_detalhe))
                else:
                    print(f"⚠️ Processo não localizado: {meta['origem']}")

            # --- ETAPA 2: Detalhamento por ID do lote ---
            if itens_para_detalhar:
                urls_detalhe = [url for _, url in itens_para_detalhar]
                res_detalhes = await collector.collect(urls_detalhe)

                for (meta, url_detalhe), res in zip(itens_para_detalhar, res_detalhes):
                    urn = meta["urn"]
                    idx = meta["index"]

                    payload_limpo = normalizar_payload_senado(res)

                    resultados[urn][idx] = criar_registro(
                        urn=urn,
                        url=url_detalhe,
                        origem=meta["origem"],
                        casa=meta["casa"],
                        sigla=meta["sigla"],
                        numero=meta["numero"],
                        ano=meta["ano"],
                        resultado=payload_limpo,
                    )

            # Checkpoint: Salva após cada lote finalizado
            salvar_progresso(output_path, resultados)
            print(f"💾 Progresso salvo em disco após o lote {lote_num}.")

            # Pausa de 1.5s entre lotes para respirar o socket do Windows e o firewall
            await asyncio.sleep(1.5)

    else:
        print("\n✅ Todas as proposições do Senado já estavam completas em cache.")

    elapsed = time.time() - start_time
    print("\n🏁 Coleta finalizada com sucesso!")
    print(f"📊 URNs processadas: {len(resultados)}")
    print(f"💾 Registros mantidos em cache: {total_sf_mantidos}")
    print(f"🌐 Proposições consultadas nesta execução: {total_pendente}")
    print(f"⏱️ Tempo total: {elapsed:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())