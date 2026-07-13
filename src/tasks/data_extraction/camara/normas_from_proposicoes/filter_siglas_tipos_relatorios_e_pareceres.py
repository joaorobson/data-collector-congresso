import json

nome_relatorio = [
    "Relatório",
    "Relatório de Subcomissão",
    "Relatório de CPI",
    "Relatório Final",
    "Relatório Prévio",
    "Relatório Prévio Reformulado",
    "Relatório Parcial",
    "Relatório Preliminar",
    "Relatório Preliminar Apresentado com Emendas",
    "Relatório de Comissão Externa",
    "Relatório de Comissão de Estudo Legislativo",
    "Relatório de Grupo de Trabalho",
    "Relatório do Congresso Nacional",
    "Relatório do Relator (CMO)",
    "Relatório Setorial",
    "Relatório de Receita",
    "Relatório do CAE",
    "Relatório do COI",
    "Relatório de Atividades do Comitê de Admissibilidade de Emendas (CAE)",
    "Relatório de Atividades do Comitê de Avaliação, Fiscalização e Controle de Execução Orçamentária",
    "Relatório de Atividades do Comitê de Avaliação, Fiscalização e Controle de Execução Orçamentária",
    "Relatório de Atividades do Comitê de Admissibilidade de Emendas (CAE)",
    "Relatório Geral",
    "Relatório Reformulado",
    "Relatório Vencedor",
    "Relatório Adotado pela Comissão",
    "Relatório Preliminar",
    "Relatório de Comissão Externa"
]

nomes_parecer =  [
    "Parecer (CD)",
    "Parecer de Comissão",
    "Parecer do Relator",
    "Parecer Vencedor",
    "Parecer Proferido em Plenário",
    "Parecer Reformulado",
    "Parecer às Emendas de Plenário",
    "Parecer às Emendas ou ao Substitutivo do Senado",
    "Parecer Técnico",
    "Parecer Reformulado de Plenário",
    "Parecer à Emenda Aglutinativa",
    "Parecer de Comissão para Redação Final",
    "Parecer Preliminar",
    "Parecer Preliminar Vencedor",
    "Parecer Preliminar de Plenário",
    "Parecer do Relator Parcial",
    "Parecer Preliminar às Emendas de Plenário",
    "Parecer às Emendas ou ao Substitutivo do Senado - Notas Taquigráficas",
    "Parecer Proferido em Plenário - Notas Taquigráficas",
    "Parecer à Redação para o Segundo Turno"
]

nomes_relatorios_e_pareceres = nome_relatorio + nomes_parecer

with open("data/camara/sigla_tipos.json", "r", encoding="utf-8") as f:
    sigla_tipos_json = json.load(f)

siglas_tipos_relatorios_e_pareceres = []

for sigla_tipo in sigla_tipos_json["dados"]:
    if sigla_tipo["nome"] in nomes_relatorios_e_pareceres:
        siglas_tipos_relatorios_e_pareceres.append(sigla_tipo["sigla"])

with open("data/camara/sigla_tipos_relatorios_e_pareceres.json", "w", encoding="utf-8") as f:
    json.dump(sorted(siglas_tipos_relatorios_e_pareceres), f)