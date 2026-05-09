import ijson
import json
from tqdm import tqdm
from datetime import datetime

materias_normalizadas = []


def parse_datetime(valor):
    if not valor:
        return None

    try:
        valor = valor.strip()

        if valor.endswith("Z"):
            valor = valor[:-1]

        valor = valor.replace("T", " ")

        return datetime.fromisoformat(valor)

    except Exception as e:
        print(f"[parse_datetime] erro ao converter: {valor} | erro: {e}")
        return None

def get_casa_origem(data: dict, autores) -> str:
    if data.get("sigla") == "PRS":
        return "SF"

    cargos = {
        a.get("sigla_cargo")
        for a in autores
        if a.get("sigla_cargo")
    }

    tipos = {
        a.get("sigla_tipo")
        for a in autores
        if a.get("sigla_tipo")
    }

    if cargos == {"DEPUTADO"}:
        return "CD"

    if cargos == {"SENADOR"}:
        return "SF"

    if tipos == {"COMISSAO_SENADO"}:
        return "SF"

    if cargos in ({"DEPUTADO", "SENADOR"},):
        return "CN"

    if tipos in (
        {"MESAS_SF_CD"},
        {"COMISSAO_SENADO_CAMARA"},
        {"COMISSAO_CONGRESSO"}
    ):
        return "CN"

    return data.get("siglaCasaIniciadora")

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

        if d.get("autoriaIniciativa"):

            for autor in d.get("autoriaIniciativa", []):

                autores.append({
                    "nome": autor.get("autor"),
                    "tipo": autor.get("descricaoTipo"),
                    "sigla_tipo": autor.get("siglaTipo"),
                    "cargo": autor.get("cargo"),
                    "sigla_cargo": autor.get("siglaCargo"),
                    "uf": None,
                    "sexo": None
                })
        elif d.get("documento", {}).get("autoria"):
            for autor in d.get("documento", {}).get("autoria", []):
                autores.append({
                    "nome": autor.get("autor"),
                    "tipo": autor.get("descricaoTipo"),
                    "sigla_tipo": autor.get("siglaTipo"),
                    "cargo": autor.get("cargo"),
                    "sigla_cargo": autor.get("siglaCargo"),
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

            nome = norma.get("descricao")
            if not nome:
                nome = f'{norma.get("tipo")} nº {norma.get("numero")}/{norma.get("anoAssinatura")}'

            norma_gerada = {
                "nome": nome,
                "ano": int(norma["anoAssinatura"]) if norma.get("anoAssinatura") else None,
                "ementa": norma.get("descricao"),
                "data_publicacao": parse_datetime(norma.get("dataPublicacao")),
                
                # extras úteis (se quiser guardar depois)
                # "data_assinatura": parse_datetime(norma.get("dataAssinatura")),
                # "veiculo_publicacao": norma.get("veiculoPublicacao"),
                # "sigla_tipo": norma.get("siglaTipo"),
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
            "casa_origem": get_casa_origem(d, autores),
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