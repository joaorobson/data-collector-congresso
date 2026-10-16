import json
import requests

siglas_tipos = requests.get("https://dadosabertos.camara.leg.br/api/v2/referencias/proposicoes/siglaTipo", headers={'accept': 'application/json'})

with open("data/camara/metadados/sigla_tipos.json", "w", encoding="utf-8") as f:
    json.dump(siglas_tipos.json(), f, indent=2, ensure_ascii=False)