import json
import re

with open("data/senado/sigla_tipos.json", "r", encoding="utf-8") as f:
    sigla_tipos_json = json.load(f)

tipos = ["projeto de lei",
         "projeto de decreto legislativo",
         "projeto de resolução",
         "proposta de emenda à constituição",
         "medida provisória",
         "proposta delegação"]

padrao_regex = r"^(" + "|".join(map(re.escape, tipos)) + r")"
sigla_tipos_filtradas = set()
for sigla_tipo in sigla_tipos_json:
    
    # Verificamos se o nome contém algum dos itens da lista
    if re.search(padrao_regex, sigla_tipo["descricao"], re.IGNORECASE):
        print(f"Encontrado: {sigla_tipo['descricao']}")
        sigla_tipos_filtradas.add(sigla_tipo["sigla"])
        # Seu código aqui...
print(f"Siglas filtradas: {sorted(sigla_tipos_filtradas)}")

with open("data/senado/sigla_tipos_proposicoes_filtradas.json", "w", encoding="utf-8") as f:
    json.dump(sorted(sigla_tipos_filtradas), f)