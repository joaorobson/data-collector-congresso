import json

INPUT_FILE = "data/normas/metadados/proposicoes_origem_normalizadas.json"

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    dados = json.load(f)

total_problemas = 0
problemas_origem = 0
problemas_casa = 0

for urn, item in dados.items():
    origem_final = item.get("origem_final")
    casas = item.get("casas")

    tem_problema = False

    # origem_final inexistente ou contendo None
    if not origem_final or any(o is None for o in origem_final):
        problemas_origem += 1
        tem_problema = True

    # casas inexistente ou contendo None
    if (
        not casas
        or len(casas) != len(origem_final or [])
        or any(c is None for c in casas)
    ):
        problemas_casa += 1
        tem_problema = True

    if tem_problema:
        total_problemas += 1
        print(f"\n{urn}")
        print("origem_final:", origem_final)
        print("casas       :", casas)

print("\n==========================")
print(f"Total de URNs analisadas : {len(dados)}")
print(f"Problemas em origem_final: {problemas_origem}")
print(f"Problemas em casas       : {problemas_casa}")
print(f"Total de URNs com problema: {total_problemas}")