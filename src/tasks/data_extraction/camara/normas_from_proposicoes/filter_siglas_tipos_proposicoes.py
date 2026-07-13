import json
import re

with open("data/camara/sigla_tipos.json", "r", encoding="utf-8") as f:
    sigla_tipos_json = json.load(f)

tipos = ["Projeto de Lei",
         "Projeto de Decreto Legislativo", 
         "Projeto de Resolução",
         "Proposta de Emenda à Constituição",
         "Medida Provisória"]

padrao_regex = r"^(" + "|".join(map(re.escape, tipos)) + r")"
sigla_tipos_filtradas = set()
for sigla_tipo in sigla_tipos_json["dados"]:
    
    # Verificamos se o nome contém algum dos itens da lista
    if re.search(padrao_regex, sigla_tipo["nome"], re.IGNORECASE):
        print(f"Encontrado: {sigla_tipo['nome']}")
        sigla_tipos_filtradas.add(sigla_tipo["sigla"])
        # Seu código aqui...
print(f"Siglas filtradas: {sorted(sigla_tipos_filtradas)}")

with open("data/camara/sigla_tipos_proposicoes.json", "w", encoding="utf-8") as f:
    json.dump(sorted(sigla_tipos_filtradas), f)