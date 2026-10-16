import os
import json
import asyncio
import random
import re

import aiohttp
from tqdm.asyncio import tqdm

CONCORRENCIA = 5
MAX_RETRIES = 8
BASE_BACKOFF = 2

INPUT_FILE = "data/normas/metadados/props_origem_sf.json"
OUTPUT_FILE = "data/normas/metadados/mpv_origem_plv.json"

URL_PROCESSO = "https://legis.senado.leg.br/dadosabertos/processo/{}?v=1"

# Regex para casar: "CMMPV 581/2012", "Medida Provisória nº 581, de 2012", "MPV 581/2012"
REGEX_CMMPV = re.compile(r"CMMPV\s+(\d+)/(\d{4})", re.IGNORECASE)
REGEX_MPV_TEXTO = re.compile(
    r"(?:Medida\s+Provis[oó]ria\s+(?:n[º°o]\s*)?|MPV\s+)(\d+)(?:[^\d]+(\d{4}))?",
    re.IGNORECASE,
)


async def consultar_detalhe_processo(session, processo_id):
    """Consulta o endpoint de processo com retries e backoff exponencial."""
    url = URL_PROCESSO.format(processo_id)

    for tentativa in range(MAX_RETRIES):
        try:
            async with session.get(url, headers={"Accept": "application/json"}) as response:
                if response.status == 200:
                    try:
                        return await response.json()
                    except Exception:
                        return None

                if response.status == 429:
                    retry_after = response.headers.get("Retry-After")
                    espera = int(retry_after) if retry_after else BASE_BACKOFF * (2**tentativa)
                    espera += random.uniform(0, 1)
                    await asyncio.sleep(espera)
                    continue

                if response.status in (404, 400):
                    return None

        except aiohttp.ClientError:
            if tentativa == MAX_RETRIES - 1:
                return None
            espera = BASE_BACKOFF * (2**tentativa) + random.uniform(0, 1)
            await asyncio.sleep(espera)

    return None


def extrair_de_texto_autoria(texto):
    """Tenta extrair número e ano da MPV a partir de strings de autoria/ente."""
    if not texto or not isinstance(texto, str):
        return None

    # Tenta padrão da sigla de comissão mista: CMMPV 581/2012
    match_cmmpv = REGEX_CMMPV.search(texto)
    if match_cmmpv:
        numero, ano = match_cmmpv.groups()
        return f"MPV {numero}/{ano}"

    # Tenta padrão descritivo: "Medida Provisória nº 581, de 2012"
    match_texto = REGEX_MPV_TEXTO.search(texto)
    if match_texto:
        numero, ano = match_texto.groups()
        if numero and ano:
            return f"MPV {numero}/{ano}"

    return None


def extrair_sigla_mpv(proc_json):
    """
    Tenta recuperar a MPV correspondente na seguinte ordem de prioridade:
    1. processosRelacionados (onde sigla == 'MPV')
    2. documento.autoria (siglaEnte, ente, autor)
    3. autoriaIniciativa (siglaEnte, ente, autor)
    4. documento.resumoAutoria
    """
    if not proc_json or not isinstance(proc_json, dict):
        return None

    # 1. Estratégia principal: processosRelacionados
    for proc in proc_json.get("processosRelacionados", []):
        if proc.get("sigla") == "MPV":
            numero = proc.get("numero")
            ano = proc.get("ano")
            if numero and ano:
                return f"MPV {numero}/{ano}"

    # 2. Fallback: documento -> autoria
    documento = proc_json.get("documento") or {}
    autores_doc = documento.get("autoria", [])
    if isinstance(autores_doc, list):
        for autor_info in autores_doc:
            candidatos = [
                autor_info.get("siglaEnte"),
                autor_info.get("ente"),
                autor_info.get("autor"),
            ]
            for cand in candidatos:
                mpv_encontrada = extrair_de_texto_autoria(cand)
                if mpv_encontrada:
                    return mpv_encontrada

    # 3. Fallback: autoriaIniciativa
    autores_iniciativa = proc_json.get("autoriaIniciativa", [])
    if isinstance(autores_iniciativa, list):
        for autor_info in autores_iniciativa:
            candidatos = [
                autor_info.get("siglaEnte"),
                autor_info.get("ente"),
                autor_info.get("autor"),
            ]
            for cand in candidatos:
                mpv_encontrada = extrair_de_texto_autoria(cand)
                if mpv_encontrada:
                    return mpv_encontrada

    # 4. Fallback: resumoAutoria
    resumo_autoria = documento.get("resumoAutoria")
    mpv_encontrada = extrair_de_texto_autoria(resumo_autoria)
    if mpv_encontrada:
        return mpv_encontrada

    return None


async def processar_plv(session, semaforo, identificacao_plv, processo_id):
    """Executa a chamada da API sob semáforo e retorna a tupla (PLV, MPV)."""
    async with semaforo:
        detalhes = await consultar_detalhe_processo(session, processo_id)
        mpv = extrair_sigla_mpv(detalhes)
        return identificacao_plv, mpv


async def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Arquivo não encontrado: {INPUT_FILE}")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        dados_sf = json.load(f)

    # Coleta todas as PLVs únicas presentes no arquivo de entrada
    plvs_para_consultar = {}
    for item in dados_sf:
        resultados = item.get("resultado")
        if isinstance(resultados, list):
            for proc in resultados:
                if proc.get("tipoDocumento") == "Projeto de Lei de Conversão":
                    identificacao = proc.get("identificacao") or proc.get("identificacaoProcessoInicial")
                    processo_id = proc.get("id")
                    if identificacao and processo_id:
                        plvs_para_consultar[identificacao.strip()] = processo_id

    print(f"Total de PLVs únicas identificadas: {len(plvs_para_consultar)}")

    # Carrega checkpoints já existentes no arquivo de saída
    mapeamento = {}
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            try:
                mapeamento = json.load(f)
            except Exception:
                mapeamento = {}

    print(f"Mapeamentos já gravados anteriormente: {len(mapeamento)}")

    # Filtra as que ainda não foram resolvidas
    pendentes = {
        plv: pid
        for plv, pid in plvs_para_consultar.items()
        if plv not in mapeamento or not mapeamento[plv]
    }
    print(f"PLVs a consultar: {len(pendentes)}")

    if not pendentes:
        print("Todas as PLVs já foram mapeadas.")
        return

    semaforo = asyncio.Semaphore(CONCORRENCIA)
    timeout = aiohttp.ClientTimeout(total=60)
    connector = aiohttp.TCPConnector(limit=CONCORRENCIA)

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        tarefas = [
            processar_plv(session, semaforo, plv, pid)
            for plv, pid in pendentes.items()
        ]

        for future in tqdm.as_completed(tarefas, total=len(tarefas)):
            identificacao_plv, mpv = await future
            if mpv:
                mapeamento[identificacao_plv] = mpv

    # Ordena o dicionário resultante pelas chaves de PLV
    mapeamento_ordenado = dict(sorted(mapeamento.items()))

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(mapeamento_ordenado, f, indent=4, ensure_ascii=False)

    print(f"\nFinalizado!")
    print(f"Arquivo gerado em: '{OUTPUT_FILE}'")
    print(f"Total de pares PLV -> MPV mapeados: {len(mapeamento_ordenado)}")


if __name__ == "__main__":
    asyncio.run(main())