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

    # 1. Se o retorno da API for uma lista diretamente no topo
    if isinstance(corpo, list):
        return {"dados": corpo}

    # 2. Se o retorno for um dicionário
    if isinstance(corpo, dict):
        if "dados" in corpo:
            return corpo

        if "processo" in corpo:
            proc = corpo.get("processo")
            return {"dados": [proc] if isinstance(proc, dict) else proc}

        if "pesquisaBasicaMateria" in corpo:
            mat = (
                corpo.get("pesquisaBasicaMateria", {})
                .get("materia", [])
            )
            return {"dados": [mat] if isinstance(mat, dict) else mat}

        return {"dados": [corpo]}

    return {"dados": []}


async def main():
    start_time = time.time()

    input_path = Path(INPUT_FILE)
    output_path = Path(OUTPUT_FILE)

    if not input_path.exists():
        raise FileNotFoundError(
            f"❌ Arquivo de entrada não encontrado:\n{input_path}"
        )

    with input_path.open("r", encoding="utf-8") as file:
        proposicoes_origem = json.load(file)

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

    urls = []
    metadata = []

    total_outras_casas = 0
    total_sf_mantidos = 0
    total_sf_coletar = 0

    # ==========================================================
    # PREPARA AS CONSULTAS
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

            # --------------------------------------------------
            # OUTRAS CASAS (CD, PR, CN, etc.):
            # Não rodam a Regex nem consultam a API do Senado.
            # --------------------------------------------------
            if casa != "SF" and casa != "CN":
                total_outras_casas += 1
                if registro_existente:
                    novos_registros.append(registro_existente)
                else:
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

            # --------------------------------------------------
            # PROPOSIÇÕES DO SENADO (SF):
            # Parse via Regex apenas se casa == "SF" ou casa == "CN"
            # --------------------------------------------------
            if origem is None:
                print(f"⚠️ Origem nula para URN {urn} no índice {idx}. Ignorando.")
                continue

            match = PATTERN.search(origem)
            if not match:
                print(f"⚠️ Não foi possível interpretar origem SF: {origem}")
                sigla, numero, ano = None, None, None
            else:
                sigla, numero, ano = match.groups()

            # --------------------------------------------------
            # CHECA SE PRECISA REPETIR A REQUISIÇÃO (SF)
            # --------------------------------------------------
            if not precisa_coletar(registro_existente):
                novos_registros.append(registro_existente)
                total_sf_mantidos += 1
                continue

            if not sigla or not numero or not ano:
                print(f"⚠️ Impossível consultar API sem sigla/número/ano: {origem}")
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

            # --------------------------------------------------
            # MONTA A URL PARA CONSULTA NO SENADO
            # --------------------------------------------------
            total_sf_coletar += 1
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
        print(f"\n🚀 Coletando {len(urls)} proposições do Senado (SF)...")

        collector = AsyncCollector(
            max_concurrent=20,
            retries=3,
        )

        raw_results = await collector.collect(urls)

        # ======================================================
        # INSERE AS RESPOSTAS NAS POSIÇÕES CORRETAS
        # ======================================================
        for meta, resposta in zip(metadata, raw_results):
            urn = meta["urn"]
            index = meta["index"]

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
        print("\n✅ Nenhuma consulta à API do Senado foi necessária nesta execução.")

    # ==========================================================
    # SALVA O ARQUIVO
    # ==========================================================

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(resultados, file, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time

    print("\n✅ Processo concluído com sucesso!")
    print(f"📊 Total de URNs processadas: {len(resultados)}")
    print(f"🏛️ Registros de outras casas (PR/CD/CN) salvos sem requisição: {total_outras_casas}")
    print(f"💾 Registros de SF mantidos de execuções anteriores: {total_sf_mantidos}")
    print(f"🌐 Novas consultas de SF executadas: {total_sf_coletar}")
    print(f"💾 Arquivo final salvo em:\n{output_path}")
    print(f"⏱️ Tempo total: {elapsed:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())