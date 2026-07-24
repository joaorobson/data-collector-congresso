import json
import requests

siglas_tipos = requests.get("https://legis.senado.gov.br/dadosabertos/processo/documento/tipos", headers={'accept': 'application/json'})

with open("data/senado/metadados/sigla_tipos.json", "w", encoding="utf-8") as f:
    json.dump(siglas_tipos.json(), f, indent=2, ensure_ascii=False)