import json

descricao_relatorios_e_pareceres = ["Relatório Legislativo", "Parecer", "Parecer de redação"]
with open("data/senado/sigla_tipos.json", "r", encoding="utf-8") as f:
    sigla_tipos_json = json.load(f)

siglas_tipos_relatorios_e_pareceres = []

for sigla_tipo in sigla_tipos_json:
    if sigla_tipo["descricao"] in descricao_relatorios_e_pareceres:
        siglas_tipos_relatorios_e_pareceres.append(sigla_tipo["sigla"])

with open("data/senado/sigla_tipos_relatorios_e_pareceres.json", "w", encoding="utf-8") as f:
    json.dump(sorted(siglas_tipos_relatorios_e_pareceres), f)