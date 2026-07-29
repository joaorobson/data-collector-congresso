import asyncio
import json
import re
import time
from pathlib import Path

from src.shared.async_collector import AsyncCollector


INPUT_FILE = "data/normas/metadados/proposicoes_origem_normalizadas.json"
OUTPUT_FILE = "data/senado/metadados/proposicoes.json"

BASE_URL = "https://legis.senado.gov.br/dadosabertos/processo"

PATTERN = re.compile(r"([A-Z]+)\s+(\d+A?)/(\d{4})")

def precisa_coletar(registro_existente) -> bool:
    """Verifica se o registro precisa ser consultado.

    Segue a mesma lógica da Câmara:
    - Retorna True se o registro for novo, se houve erro/status != 200
      ou se 'dados' for None / lista vazia ([]).
    - Retorna False APENAS quando 'dados' possui conteúdo.
    """
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
    if not dados:  # Avalia True para None, [], etc.
        return True

    return False


def criar_registro(
    urn,
    url,
    origem,
    casa,
    sigla,
    numero,
    ano,
    resultado,
):
    """Cria um registro no formato padrão do arquivo do Senado."""
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

def normalizar_payload_senado(resposta_collector):
    """Extrai o corpo retornado pelo AsyncCollector e padroniza sob a chave 'dados'."""
    if not isinstance(resposta_collector, dict):
        return {"dados": []}

    corpo = resposta_collector.get("resultado")

    # 1. Se o retorno da API for uma lista diretamente no topo (ex: [{ "id": 7790932, ... }])
    if isinstance(corpo, list):
        return {"dados": corpo}

    # 2. Se o retorno for um dicionário
    if isinstance(corpo, dict):
        # Se já estiver padronizado
        if "dados" in corpo:
            return corpo

        # Se for o formato de pesquisa /materia ou /processo com nó interno
        if "processo" in corpo:
            proc = corpo.get("processo")
            return {"dados": [proc] if isinstance(proc, dict) else proc}

        if "pesquisaBasicaMateria" in corpo:
            mat = (
                corpo.get("pesquisaBasicaMateria", {})
                .get("materia", [])
            )
            return {"dados": [mat] if isinstance(mat, dict) else mat}

        # Dicionário único (ex: payload de um único item)
        return {"dados": [corpo]}

    return {"dados": []}


async def main():
    start_time = time.time()

    input_path = Path(INPUT_FILE)
    output_path = Path(OUTPUT_FILE)

    # ==========================================================
    # LÊ O ARQUIVO DE ORIGEM
    # ==========================================================

    if not input_path.exists():
        raise FileNotFoundError(
            f"❌ Arquivo de entrada não encontrado:\n{input_path}"
        )

    with input_path.open("r", encoding="utf-8") as file:
        proposicoes_origem = json.load(file)

    # ==========================================================
    # LÊ OS RESULTADOS JÁ SALVOS
    # ==========================================================

    resultados = {}

    if output_path.exists():
        print(f"📂 Carregando resultados existentes:\n{output_path}")
        with output_path.open("r", encoding="utf-8") as file:
            try:
                resultados = json.load(file)
            except json.JSONDecodeError:
                print(
                    "⚠️ O arquivo existente possui JSON inválido. Será iniciado um novo arquivo."
                )
                resultados = {}
    else:
        print("📂 Nenhum arquivo anterior encontrado. Iniciando nova coleta.")

    # ==========================================================
    # PREPARA AS CONSULTAS
    # ==========================================================

    urls = []
    metadata = []

    total_mantidos = 0
    total_cd_ignorados = 0

    for urn, prop in proposicoes_origem.items():
        origens = prop.get("origem_final") or []
        casas = prop.get("casas") or [None] * len(origens)

        registros_atuais = resultados.get(urn, [])
        novos_registros = []

        for idx, (origem, casa) in enumerate(zip(origens, casas)):
            match = PATTERN.search(origem)

            if not match:
                print(f"⚠️ Não foi possível interpretar: {origem}")
                continue

            sigla, numero, ano = match.groups()

            # ==================================================
            # NÃO CONSULTA PROPOSIÇÕES DA CÂMARA
            # ==================================================
            if casa == "CD":
                total_cd_ignorados += 1
                registro_existente = (
                    registros_atuais[idx]
                    if idx < len(registros_atuais)
                    else None
                )

                if registro_existente:
                    novos_registros.append(registro_existente)
                else:
                    novos_registros.append(
                        {
                            "origem": origem,
                            "casa": casa,
                            "sigla": sigla,
                            "numero": numero,
                            "ano": ano,
                            "resultado": {"dados": []},
                        }
                    )
                continue

            # ==================================================
            # CONSULTA SOMENTE REGISTROS SEM RESULTADO
            # ==================================================
            registro_existente = (
                registros_atuais[idx] if idx < len(registros_atuais) else None
            )

            if not precisa_coletar(registro_existente):
                novos_registros.append(registro_existente)
                total_mantidos += 1
                continue

            # ==================================================
            # MONTA A URL PARA NOVA CONSULTA
            # ==================================================
            url = f"{BASE_URL}?sigla={sigla}&numero={numero}&ano={ano}&v=1"

            urls.append(url)
            metadata.append(
                {
                    "urn": urn,
                    "index": idx,
                    "url": url,
                    "origem": origem,
                    "casa": casa,
                    "sigla": sigla,
                    "numero": numero,
                    "ano": ano,
                }
            )

            novos_registros.append(
                criar_registro(
                    urn=urn,
                    url=url,
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
    # EXECUTA AS NOVAS CONSULTAS
    # ==========================================================

    if urls:
        print(f"\n🚀 Coletando {len(urls)} proposições do Senado...")

        collector = AsyncCollector(
            max_concurrent=20,
            retries=3,
        )

        raw_results = await collector.collect(urls)

        # ======================================================
        # INSERE AS RESPOSTAS NAS POSIÇÕES CORRETAS (SEM ANINHAMENTO DUPLO)
        # ======================================================
        for meta, resposta in zip(metadata, raw_results):
            urn = meta["urn"]
            index = meta["index"]

            # Extrai apenas o payload limpo de dentro da resposta do AsyncCollector
            payload_limpo = normalizar_payload_senado(resposta)

            resultados[urn][index] = criar_registro(
                urn=urn,
                url=meta["url"],
                origem=meta["origem"],
                casa=meta["casa"],
                sigla=meta["sigla"],
                numero=meta["numero"],
                ano=meta["ano"],
                resultado=payload_limpo,
            )
    else:
        print("\n✅ Nenhuma coleta necessária.")

    # ==========================================================
    # SALVA O ARQUIVO
    # ==========================================================

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(resultados, file, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time

    print("\n✅ Processo concluído!")
    print(f"📊 Total de URNs: {len(resultados)}")
    print(f"🏛️ Registros da CD ignorados: {total_cd_ignorados}")
    print(f"💾 Resultados existentes mantidos: {total_mantidos}")
    print(f"🌐 Novas consultas realizadas: {len(urls)}")
    print(f"💾 Arquivo salvo em:\n{output_path}")
    print(f"⏱️ Tempo total: {elapsed:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())