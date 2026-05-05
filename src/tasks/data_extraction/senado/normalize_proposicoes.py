import ijson
import json
from tqdm import tqdm
from datetime import datetime

materias_normalizadas = []


def parse_datetime(valor):
    if not valor:
        return None

    try:
        return datetime.fromisoformat(valor)
    except:
        return None


with open(
    "data/senado/detalhes_proposicoes.json",
    "r",
    encoding="utf-8"
) as f:
    objects = ijson.items(f, 'item')
    for i, d in enumerate(tqdm(objects, desc="Processando proposições", unit=" proposições")):

        # =========================
        # EMENTA
        # =========================
        ementa = (
            d.get("conteudo", {})
            .get("ementa", "")
            .strip()
        )

        # =========================
        # DATA APRESENTAÇÃO
        # =========================
        data_apresentacao = parse_datetime(
            d.get("documento", {})
            .get("dataApresentacao")
        )

        # =========================
        # PALAVRAS CHAVE
        # =========================
        indexacao = (
            d.get("documento", {})
            .get("indexacao", "")
        )

        palavras_chave = [
            p.strip()
            for p in indexacao.split(",")
            if p.strip()
        ]

        # =========================
        # AUTORIA
        # =========================
        autores = []

        for autor in d.get("documento", {}).get("autoria", []):

            autores.append({
                "nome": autor.get("autor"),
                "tipo": autor.get("descricaoTipo"),
                "uf": None,
                "sexo": None
            })

        # =========================
        # SITUAÇÃO
        # =========================
        situacao_atual = None

        autuacoes = d.get("autuacoes", [])

        if autuacoes:
            situacoes = autuacoes[0].get("situacoes", [])

            if situacoes:
                situacao_atual = situacoes[-1].get("descricao")

        # =========================
        # TRAMITANDO
        # =========================
        tramitando = (
            d.get("tramitando", "")
            .strip()
            .lower() == "sim"
        )

        # =========================
        # NORMA GERADA
        # =========================
        norma_gerada = None

        if d.get("normaGerada"):

            norma = d["normaGerada"]

            norma_gerada = {
                "nome": norma.get("identificacao"),
                "ano": norma.get("ano"),
                "ementa": norma.get("ementa"),
                "data_publicacao": parse_datetime(
                    norma.get("dataPublicacao")
                )
            }

        # =========================
        # TRANSFORMADO EM NORMA
        # =========================
        transformado_em_norma = bool(d.get("normaGerada"))
    
        # =========================
        # OUTROS NOMES
        # =========================
        outros_nomes = []
        # 1. A partir de outrosNumeros
        for outro in d.get("outrosNumeros", []):

            sigla = outro.get("sigla")
            numero = outro.get("numero")
            ano = outro.get("ano")
            casa = outro.get("casaIdentificadora")

            if sigla and numero and ano:
                numero_limpo = str(numero).replace(".", "").replace(",", "").strip()

                try:
                    numero_int = int(numero_limpo)
                except ValueError:
                    # fallback: mantém como string se não der pra converter
                    numero_int = numero_limpo

                nome_formatado = f"{sigla} {numero_int}/{ano}"
                outros_nomes.append({
                    "nome": nome_formatado,
                    "casa": casa
                })

        # =========================
        # OBJETO FINAL
        # =========================
        materia = {
            "id": d.get("id"),
            "uri": f"https://legis.senado.leg.br/dadosabertos/processo/{d.get('id')}?v=1",
            "ano": d.get("ano"),
            "nome": d.get("identificacao"),
            "nome_inicial": d.get("identificacaoProcessoInicial"),
            "numero": d.get("numero"),
            "ementa": ementa,
            "data_apresentacao": data_apresentacao,
            "palavras_chave": palavras_chave,
            "autoria": autores,
            "situacao_atual": situacao_atual,
            "em_tramitacao": tramitando,
            "casa_atual": d.get("casaIdentificadora"),
            "casa_origem": d.get("siglaCasaIniciadora"),
            "outros_nomes": outros_nomes,
            "transformado_em_norma": transformado_em_norma,
            "norma_gerada": norma_gerada,

            # auxiliares para conversão posterior
            "sigla_tipo": d.get("sigla"),
            "tipo": d.get("descricaoSigla")
        }

        materias_normalizadas.append(materia)


def json_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()

    raise TypeError(f"Type {type(obj)} not serializable")

with open("data/senado/proposicoes_normalizadas.json", "w", encoding="utf-8") as f:
    json.dump(materias_normalizadas, f, ensure_ascii=False, indent=2, default=json_serializer)