import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.shared.async_collector import AsyncCollector


INPUT_FILE = "data/camara/metadados/proposicoes.json"
OUTPUT_FILE = "data/camara/metadados/autoria_proposicoes.json"


def precisa_coletar(
    registro_existente: Optional[Dict[str, Any]],
    uri_autores: Optional[str],
) -> bool:
    """
    Verifica se um registro de autores precisa ser coletado novamente.

    Um registro é considerado válido em cache quando:
    - existe;
    - possui resultado como dict;
    - não possui erro;
    - se houver status, ele é 200;
    - possui 'dados' como lista;
    - a URL armazenada é a mesma uriAutores da proposição.

    Importante:
    dados=[] é considerado uma resposta válida.
    """

    if not registro_existente:
        return True

    # Verifica se a URL armazenada corresponde à uriAutores atual.
    if registro_existente.get("url") != uri_autores:
        return True

    resultado = registro_existente.get("resultado")

    if not isinstance(resultado, dict):
        return True

    # Erro explícito.
    if resultado.get("erro"):
        return True

    # Caso o collector tenha armazenado status.
    status = resultado.get("status")

    if status is not None and status != 200:
        return True

    # Uma resposta válida pode possuir zero autores.
    if "dados" not in resultado:
        return True

    if not isinstance(resultado.get("dados"), list):
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
    """
    Cria um registro no mesmo formato do arquivo de proposições.
    """

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


def extrair_proposicao(
    registro: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Extrai os dados da proposição do registro original.

    Espera:

    {
        "resultado": {
            "dados": [
                {
                    ...
                    "uriAutores": "..."
                }
            ]
        }
    }
    """

    resultado = registro.get("resultado")

    if not isinstance(resultado, dict):
        return None

    dados = resultado.get("dados")

    if not isinstance(dados, list):
        return None

    if len(dados) == 0:
        return None

    proposicao = dados[0]

    if not isinstance(proposicao, dict):
        return None

    return proposicao


def extrair_uri_autores(
    registro: Dict[str, Any],
) -> Optional[str]:
    """
    Obtém a uriAutores da proposição.
    """

    proposicao = extrair_proposicao(registro)

    if not proposicao:
        return None

    uri_autores = proposicao.get("uriAutores")

    if not isinstance(uri_autores, str):
        return None

    uri_autores = uri_autores.strip()

    if not uri_autores:
        return None

    return uri_autores


def normalizar_resultado(
    resposta: Any,
) -> Dict[str, Any]:
    """
    Normaliza a resposta do AsyncCollector preservando:

        resultado:
        {
            "dados": [...],
            "links": [...]
        }

    O endpoint de autores retorna:

        {
          "dados": [...],
          "links": [...]
        }

    O AsyncCollector, conforme o formato utilizado no primeiro script,
    encapsula esse conteúdo em:

        {
          "resultado": {
            "dados": [...],
            "links": [...]
          }
        }

    Aqui preservamos dados e links.
    """

    if not isinstance(resposta, dict):
        return {
            "dados": []
        }

    resultado_api = resposta.get("resultado")

    if not isinstance(resultado_api, dict):
        return {
            "dados": []
        }

    # ----------------------------------------------------------
    # DADOS
    # ----------------------------------------------------------

    dados = resultado_api.get("dados", [])

    if isinstance(dados, list):
        dados_normalizados = dados

    elif isinstance(dados, dict):
        dados_normalizados = [dados]

    else:
        dados_normalizados = []

    # ----------------------------------------------------------
    # LINKS
    # ----------------------------------------------------------

    links = resultado_api.get("links", [])

    if isinstance(links, list):
        links_normalizados = links

    elif isinstance(links, dict):
        links_normalizados = [links]

    else:
        links_normalizados = []

    resultado = {
        "dados": dados_normalizados,
        "links": links_normalizados,
    }

    # ----------------------------------------------------------
    # PRESERVA CAMPOS EXTRAS DO COLLECTOR, SE EXISTIREM
    # ----------------------------------------------------------
    #
    # Caso o AsyncCollector retorne, por exemplo:
    #
    # {
    #     "resultado": {
    #         "dados": [...],
    #         "links": [...]
    #     },
    #     "status": 200
    # }
    #
    # não precisamos necessariamente armazenar status.
    #
    # O objetivo é manter o mesmo payload estrutural da API.
    #

    return resultado


async def main():
    start_time = time.time()

    input_path = Path(INPUT_FILE)
    output_path = Path(OUTPUT_FILE)

    # ==========================================================
    # VALIDAÇÃO DO INPUT
    # ==========================================================

    if not input_path.exists():
        raise FileNotFoundError(
            f"❌ Arquivo de entrada não encontrado: {input_path}"
        )

    print(f"📂 Carregando proposições de: {input_path}")

    with input_path.open("r", encoding="utf-8") as f:
        proposicoes = json.load(f)

    if not isinstance(proposicoes, dict):
        raise ValueError(
            "❌ O arquivo de proposições deve conter um objeto JSON "
            "indexado por URN."
        )

    # ==========================================================
    # CARREGA CACHE
    # ==========================================================

    resultados_existentes: Dict[str, List[Dict[str, Any]]] = {}

    if output_path.exists():

        print(
            f"📂 Carregando base de autores existente: "
            f"{output_path}"
        )

        try:
            with output_path.open("r", encoding="utf-8") as f:
                resultados_existentes = json.load(f)

            if not isinstance(resultados_existentes, dict):
                print(
                    "⚠️ Base existente não possui o formato esperado. "
                    "Reiniciando."
                )
                resultados_existentes = {}

        except json.JSONDecodeError:
            print(
                "⚠️ JSON de autores corrompido ou inválido. "
                "Reiniciando base."
            )
            resultados_existentes = {}

    # ==========================================================
    # ESTRUTURAS
    # ==========================================================

    resultados: Dict[str, List[Dict[str, Any]]] = {}

    metadata_para_coleta: List[Dict[str, Any]] = []

    # ==========================================================
    # CONTADORES
    # ==========================================================

    total_urns = 0
    total_registros = 0

    total_cd = 0
    total_outras_casas = 0

    total_com_uri_autores = 0
    total_sem_uri_autores = 0

    total_cache = 0
    total_coletar = 0

    # ==========================================================
    # PREPARAÇÃO DAS FILAS
    # ==========================================================

    print("\n🔎 Preparando registros para coleta...")

    for urn, registros_proposicao in proposicoes.items():

        total_urns += 1

        # Segurança para entradas inesperadas.
        if not isinstance(registros_proposicao, list):
            resultados[urn] = []
            continue

        registros_existentes = resultados_existentes.get(urn, [])

        if not isinstance(registros_existentes, list):
            registros_existentes = []

        novos_registros: List[Dict[str, Any]] = []

        # ------------------------------------------------------
        # Cada URN pode possuir uma ou mais ocorrências:
        #
        # CD
        # SF
        # CN
        # etc.
        # ------------------------------------------------------

        for idx, registro_proposicao in enumerate(
            registros_proposicao
        ):

            total_registros += 1

            if not isinstance(registro_proposicao, dict):

                novos_registros.append(
                    criar_registro(
                        urn=urn,
                        url="",
                        origem=None,
                        casa=None,
                        sigla=None,
                        numero=None,
                        ano=None,
                        resultado={
                            "dados": []
                        },
                    )
                )

                continue

            origem = registro_proposicao.get("origem")
            casa = registro_proposicao.get("casa")
            sigla = registro_proposicao.get("sigla")
            numero = registro_proposicao.get("numero")
            ano = registro_proposicao.get("ano")

            # ==================================================
            # OUTRAS CASAS
            # ==================================================

            if casa != "CD":

                total_outras_casas += 1

                novos_registros.append(
                    criar_registro(
                        urn=urn,
                        url="",
                        origem=origem,
                        casa=casa,
                        sigla=sigla,
                        numero=numero,
                        ano=ano,
                        resultado={
                            "dados": []
                        },
                    )
                )

                continue

            # ==================================================
            # CÂMARA
            # ==================================================

            total_cd += 1

            # --------------------------------------------------
            # Obtém uriAutores do resultado da primeira coleta.
            # --------------------------------------------------

            uri_autores = extrair_uri_autores(
                registro_proposicao
            )

            # --------------------------------------------------
            # Sem uriAutores
            # --------------------------------------------------

            if not uri_autores:

                total_sem_uri_autores += 1

                novos_registros.append(
                    criar_registro(
                        urn=urn,
                        url="",
                        origem=origem,
                        casa=casa,
                        sigla=sigla,
                        numero=numero,
                        ano=ano,
                        resultado={
                            "dados": []
                        },
                    )
                )

                continue

            total_com_uri_autores += 1

            # ==================================================
            # CACHE
            # ==================================================

            registro_existente = (
                registros_existentes[idx]
                if idx < len(registros_existentes)
                else None
            )

            if not precisa_coletar(
                registro_existente,
                uri_autores,
            ):

                novos_registros.append(
                    registro_existente
                )

                total_cache += 1

                continue

            # ==================================================
            # NOVA COLETA
            # ==================================================

            metadata_para_coleta.append(
                {
                    "urn": urn,
                    "index": idx,
                    "origem": origem,
                    "casa": casa,
                    "sigla": sigla,
                    "numero": numero,
                    "ano": ano,
                    "uri_autores": uri_autores,
                }
            )

            total_coletar += 1

            # --------------------------------------------------
            # Placeholder
            # --------------------------------------------------

            novos_registros.append(
                criar_registro(
                    urn=urn,
                    url=uri_autores,
                    origem=origem,
                    casa=casa,
                    sigla=sigla,
                    numero=numero,
                    ano=ano,
                    resultado={
                        "dados": []
                    },
                )
            )

        resultados[urn] = novos_registros

    # ==========================================================
    # RESUMO DA PREPARAÇÃO
    # ==========================================================

    print("\n" + "=" * 70)
    print("📊 RESUMO DA PREPARAÇÃO")
    print("=" * 70)

    print(f"URNs:                    {total_urns}")
    print(f"Registros:               {total_registros}")
    print(f"Registros CD:            {total_cd}")
    print(f"Outras casas:            {total_outras_casas}")
    print(f"Com uriAutores:          {total_com_uri_autores}")
    print(f"Sem uriAutores:          {total_sem_uri_autores}")
    print(f"Cache:                   {total_cache}")
    print(f"Para coletar:            {total_coletar}")

    # ==========================================================
    # COLETA
    # ==========================================================

    if metadata_para_coleta:

        print("\n" + "=" * 70)
        print("🚀 COLETA DE AUTORES")
        print("=" * 70)

        collector = AsyncCollector(
            max_concurrent=15,
            retries=3,
        )

        urls_autores = [
            meta["uri_autores"]
            for meta in metadata_para_coleta
        ]

        print(
            f"🌐 Consultando {len(urls_autores)} "
            f"endpoints de autores..."
        )

        # ------------------------------------------------------
        # Coleta assíncrona em lote
        # ------------------------------------------------------

        respostas = await collector.collect(
            urls_autores
        )

        # ======================================================
        # PROCESSAMENTO DAS RESPOSTAS
        # ======================================================

        total_sucesso = 0
        total_vazio = 0
        total_erro = 0

        for meta, resposta in zip(
            metadata_para_coleta,
            respostas,
        ):

            urn = meta["urn"]
            index = meta["index"]
            uri_autores = meta["uri_autores"]

            # --------------------------------------------------
            # Normaliza resposta
            # --------------------------------------------------

            resultado_api = normalizar_resultado(
                resposta
            )

            dados = resultado_api.get(
                "dados",
                []
            )

            # --------------------------------------------------
            # Estatísticas
            # --------------------------------------------------

            if dados:

                total_sucesso += 1

            else:

                total_vazio += 1

            # --------------------------------------------------
            # Atualiza registro
            # --------------------------------------------------

            resultados[urn][index] = criar_registro(
                urn=urn,
                url=uri_autores,
                origem=meta["origem"],
                casa=meta["casa"],
                sigla=meta["sigla"],
                numero=meta["numero"],
                ano=meta["ano"],
                resultado=resultado_api,
            )

        print("\n📊 Resultado da coleta:")
        print(f"   Com autores: {total_sucesso}")
        print(f"   Sem autores: {total_vazio}")
        print(f"   Erros:       {total_erro}")

    else:

        print(
            "\n✅ Nenhuma nova consulta necessária. "
            "Todos os registros estão em cache."
        )

    # ==========================================================
    # PERSISTÊNCIA
    # ==========================================================

    print(
        f"\n💾 Salvando resultado em: {output_path}"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            resultados,
            f,
            ensure_ascii=False,
            indent=2,
        )

    # ==========================================================
    # ESTATÍSTICAS FINAIS
    # ==========================================================

    elapsed = time.time() - start_time

    print("\n" + "=" * 70)
    print("✅ COLETA CONCLUÍDA")
    print("=" * 70)

    print(f"📊 URNs processadas:           {total_urns}")
    print(f"📋 Registros processados:      {total_registros}")
    print(f"🏛️ Registros CD:               {total_cd}")
    print(
        f"🏛️ Outras casas:               "
        f"{total_outras_casas}"
    )
    print(
        f"🔗 Com uriAutores:             "
        f"{total_com_uri_autores}"
    )
    print(
        f"⚠️ Sem uriAutores:             "
        f"{total_sem_uri_autores}"
    )
    print(
        f"💾 Mantidos em cache:          "
        f"{total_cache}"
    )
    print(
        f"🌐 Novas consultas:            "
        f"{total_coletar}"
    )
    print(f"📁 Arquivo final:              {output_path}")
    print(f"⏱️ Tempo total:                {elapsed:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())