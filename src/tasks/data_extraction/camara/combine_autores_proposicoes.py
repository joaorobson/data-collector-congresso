import json
from tqdm import tqdm

with open("data/camara/detalhes_proposicoes.json", "r", encoding="utf-8") as f:
    detalhes_proposicoes = json.load(f)

with open("data/camara/autores_proposicoes.json", "r", encoding="utf-8") as f:
    autores_proposicoes = json.load(f)

proposicoes = []

for detalhe in tqdm(detalhes_proposicoes):
    id_ = detalhe["id"]
    autoria = autores_proposicoes.get(str(id_), {"autores": []})["autores"]
    detalhe["autoria"] = autoria
    proposicoes.append(detalhe)


with open("data/camara/proposicoes_com_autoria.json", 'w', encoding='utf-8') as f:
    json.dump(proposicoes, f, ensure_ascii=False, indent=2)