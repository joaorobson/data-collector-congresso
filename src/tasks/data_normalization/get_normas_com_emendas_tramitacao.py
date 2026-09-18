import os
from pathlib import Path
import pandas as pd




# 2. Salvar base completa (Dataset Full)
normas_df = pd.read_parquet("data/datasets/full/normas.parquet")
proposicoes_df = pd.read_parquet("data/datasets/full/proposicoes.parquet")
emendas_df = pd.read_parquet("data/datasets/full/emendas.parquet")
relatorios_df = pd.read_parquet("data/datasets/full/relatorios.parquet")

# 3. Filtrar normas cuja tramitação teve ao menos 1 emenda
# a) IDs de proposições que possuem emendas registradas
id_props_com_emenda = set(emendas_df["id_proposicao"].unique())

# b) URNs das normas que contêm ao menos uma dessas proposições
urns_normas_com_emenda = set(
    proposicoes_df[proposicoes_df["id"].isin(id_props_com_emenda)]["urn_norma"].unique()
)

# c) Subconjuntos relacionais consistentes
normas_emendas_df = normas_df[normas_df["urn"].isin(urns_normas_com_emenda)]

# Pega TODAS as proposições das normas qualificadas (mesmo as que não tiveram emenda individual)
proposicoes_emendas_df = proposicoes_df[proposicoes_df["urn_norma"].isin(urns_normas_com_emenda)]
ids_proposicoes_filtradas = set(proposicoes_emendas_df["id"].unique())

# Emendas e relatórios vinculados a essas proposições
emendas_filtradas_df = emendas_df[emendas_df["id_proposicao"].isin(ids_proposicoes_filtradas)]
relatorios_filtrados_df = relatorios_df[relatorios_df["id_proposicao"].isin(ids_proposicoes_filtradas)]

# 4. Salvar base filtrada (Dataset com Emendas)
normas_emendas_df.to_parquet("data/datasets/com_emendas/normas.parquet", index=False)
proposicoes_emendas_df.to_parquet("data/datasets/com_emendas/proposicoes.parquet", index=False)
emendas_filtradas_df.to_parquet("data/datasets/com_emendas/emendas.parquet", index=False)
relatorios_filtrados_df.to_parquet("data/datasets/com_emendas/relatorios.parquet", index=False)

print(f"Normas com emenda: {len(normas_emendas_df)} de {len(normas_df)}")
print(f"Proposições relacionadas: {len(proposicoes_emendas_df)} de {len(proposicoes_df)}")