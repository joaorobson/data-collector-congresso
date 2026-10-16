import json

descricao_emendas = ["Emenda na Comissão", "Emenda de Plenário", "Emenda/Substitutivo do Senado", 
                      "Substitutivo", "Subemenda", "Emenda de Relator", "Emenda ao Substitutivo",
                      "Emenda à LDO", "Emenda ao Orçamento", "Emenda", "Emenda de Redação",
                      "Emenda Substitutiva de Plenário", "Subemenda Substitutiva de Plenário",
                      "Emenda Aglutinativa", "Emenda de Relator Parcial", "Emenda Adotada pela Comissão",
                      "Subemenda Adotada pela Comissão", "Emenda à Medida Provisória (CN)", "Subemenda de Relator",
                      "Emenda de Redação Adotada", "Emenda Aglutinativa Substitutiva", "Emenda à PEC",
                      "Emenda de Plenário a Projeto com Urgência ",
                      "Emenda de Plenário a Projeto em Fase de Discussão do 2º Turno",
                      "Emenda de Redação em Plenário", "Emenda de Plenário à MPV (Ato Conjunto 1/20)", "Emenda (CN)"]

with open("data/camara/metadados/sigla_tipos.json", "r", encoding="utf-8") as f:
    sigla_tipos_json = json.load(f)

siglas_tipos_emendas= []

for sigla_tipo in sigla_tipos_json["dados"]:
    if sigla_tipo["nome"] in descricao_emendas:
        siglas_tipos_emendas.append(sigla_tipo["sigla"])

with open("data/camara/metadados/sigla_tipos_emendas.json", "w", encoding="utf-8") as f:
    json.dump(sorted(siglas_tipos_emendas), f)