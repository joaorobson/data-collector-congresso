from pathlib import Path
import pandas as pd

# -------------------------------------------------------------------------
# CONFIGURAÇÃO DE PARÂMETROS
# -------------------------------------------------------------------------
MIN_EMENDAS_ETAPA = 41  # Limiar mínimo de emendas em pelo menos UMA etapa

# 1. Carregar base completa
normas_df = pd.read_parquet("data/datasets/full/normas.parquet")
proposicoes_df = pd.read_parquet("data/datasets/full/proposicoes.parquet")
emendas_df = pd.read_parquet("data/datasets/full/emendas.parquet")
relatorios_df = pd.read_parquet("data/datasets/full/relatorios.parquet")

# -------------------------------------------------------------------------
# FILTRO 0: Exclusão de proposições orçamentárias (ex: PLNs, LDO, LOA)
# -------------------------------------------------------------------------
coluna_tipo = "sigla_tipo" if "sigla_tipo" in proposicoes_df.columns else "tipo"

is_pln_nome = (
    proposicoes_df["nome"]
    .astype(str)
    .str.strip()
    .str.upper()
    .str.startswith("PLN")
)

# Identifica URNs associadas a qualquer proposição estritamente orçamentária
urns_com_pln = set(
    proposicoes_df[is_pln_nome]["urn_norma"].dropna().unique()
)

# Remove as proposições vinculadas a essas URNs orçamentárias logo na raiz
proposicoes_df = proposicoes_df[~proposicoes_df["urn_norma"].isin(urns_com_pln)].copy()

# -------------------------------------------------------------------------
# FILTRO 1: Pelo menos uma etapa (id_proposicao) com >= MIN_EMENDAS_ETAPA
# -------------------------------------------------------------------------
emendas_com_norma = emendas_df.merge(
    proposicoes_df[["id", "urn_norma"]],
    left_on="id_proposicao",
    right_on="id",
    how="inner",
)

# Conta emendas agrupadas por norma e etapa (proposição)
emendas_por_etapa = (
    emendas_com_norma.groupby(["urn_norma", "id_proposicao"])["id_x"]
    .count()
    .rename("total_emendas_etapa")
)

# Identifica o pico de emendas de uma única etapa para cada norma
max_emendas_por_norma = emendas_por_etapa.groupby("urn_norma").max()

# Seleciona as normas cuja etapa máxima atinge o limiar estipulado
urns_candidatas_qtd = set(
    max_emendas_por_norma[max_emendas_por_norma >= MIN_EMENDAS_ETAPA].index
)

# -------------------------------------------------------------------------
# FILTRO 2: Validação de URLs das Proposições
# - Proposição comum: deve ter url_texto_inicial E url_autografo
# - Veto: deve ter url_texto_inicial (não exige url_autografo)
# -------------------------------------------------------------------------
is_veto = (
    proposicoes_df[coluna_tipo].astype(str).str.strip().str.upper().str.contains("VET")
)

tem_texto_inicial = (
    proposicoes_df["avulso_inicial_url_doc"].notna()
    & (proposicoes_df["avulso_inicial_url_doc"].astype(str).str.strip() != "")
)

tem_autografo = (
    proposicoes_df["autografo_url_doc"].notna()
    & (proposicoes_df["autografo_url_doc"].astype(str).str.strip() != "")
)

prop_valida_url = (is_veto & tem_texto_inicial) | (~is_veto & tem_texto_inicial & tem_autografo)

urns_com_falha_url_prop = set(
    proposicoes_df[~prop_valida_url]["urn_norma"].dropna().unique()
)

# -------------------------------------------------------------------------
# FILTRO 3: Validação de url_doc nas Emendas
# -------------------------------------------------------------------------
emenda_tem_url_doc = (
    emendas_df["url_doc"].notna()
    & (emendas_df["url_doc"].astype(str).str.strip() != "")
)

# IDs de proposições que contêm alguma emenda sem url_doc
props_com_emenda_sem_url = set(
    emendas_df[~emenda_tem_url_doc]["id_proposicao"].dropna().unique()
)

urns_com_falha_url_emenda = set(
    proposicoes_df[proposicoes_df["id"].isin(props_com_emenda_sem_url)][
        "urn_norma"
    ].dropna().unique()
)

# -------------------------------------------------------------------------
# FILTRO 4: Validação de url_doc nos Relatórios (se houver emenda, deve ter relatório válido)
# -------------------------------------------------------------------------
relatorio_tem_url_doc = (
    relatorios_df["url_doc"].notna()
    & (relatorios_df["url_doc"].astype(str).str.strip() != "")
)

props_com_emenda = set(emendas_df["id_proposicao"].dropna().unique())
props_com_relatorio_valido = set(
    relatorios_df[relatorio_tem_url_doc]["id_proposicao"].dropna().unique()
)

# Proposições que possuem emendas mas não possuem nenhum relatório com url_doc válido
props_emenda_sem_relatorio = props_com_emenda - props_com_relatorio_valido

urns_com_falha_relatorio = set(
    proposicoes_df[proposicoes_df["id"].isin(props_emenda_sem_relatorio)][
        "urn_norma"
    ].dropna().unique()
)

# -------------------------------------------------------------------------
# CONSOLIDAÇÃO DOS CRITÉRIOS
# -------------------------------------------------------------------------
urns_validas = (
    urns_candidatas_qtd
    - urns_com_falha_url_prop
    - urns_com_falha_url_emenda
    - urns_com_falha_relatorio
)

# -------------------------------------------------------------------------
# FILTRAGEM FINAL DOS DATASETS (Atomicidade da Norma Preservada)
# -------------------------------------------------------------------------
normas_filtradas_df = normas_df[normas_df["urn"].isin(urns_validas)].copy()

# Todas as proposições vinculadas às normas qualificadas são retidas integralmente
proposicoes_filtradas_df = proposicoes_df[
    proposicoes_df["urn_norma"].isin(urns_validas)
].copy()
ids_proposicoes_validas = set(proposicoes_filtradas_df["id"].unique())

# Emendas e relatórios vinculados a qualquer uma das proposições das normas qualificadas
emendas_filtradas_df = emendas_df[
    emendas_df["id_proposicao"].isin(ids_proposicoes_validas)
].copy()

relatorios_filtrados_df = relatorios_df[
    relatorios_df["id_proposicao"].isin(ids_proposicoes_validas)
].copy()

# -------------------------------------------------------------------------
# EXPORTAÇÃO
# -------------------------------------------------------------------------
output_dir = Path("data/datasets/experiments")
output_dir.mkdir(parents=True, exist_ok=True)

normas_filtradas_df.to_parquet(output_dir / "normas.parquet", index=False)
proposicoes_filtradas_df.to_parquet(output_dir / "proposicoes.parquet", index=False)
emendas_filtradas_df.to_parquet(output_dir / "emendas.parquet", index=False)
relatorios_filtrados_df.to_parquet(output_dir / "relatorios.parquet", index=False)

print(f"Normas qualificadas: {len(normas_filtradas_df)} de {len(normas_df)}")
print(f"Proposições vinculadas: {len(proposicoes_filtradas_df)} de {len(proposicoes_df)}")
print(f"Emendas vinculadas: {len(emendas_filtradas_df)} de {len(emendas_df)}")
print(f"Relatórios vinculados: {len(relatorios_filtrados_df)} de {len(relatorios_df)}")