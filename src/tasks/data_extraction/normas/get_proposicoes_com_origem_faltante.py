import json

with open("data/normas/metadados/normas.json", "r", encoding="utf-8") as f:
    normas = json.load(f)

with open("data/normas/metadados/proposicoes_de_origem_da_norma_from_normas_leg_br.json", "r", encoding="utf-8") as f:
    origens = json.load(f)

source_by_urn = {
    item["urn"]: item.get("sourceProcess")
    for item in origens
}

sem_relacionamento_e_sem_source = []

for norma in normas:

    urn = norma.get("urn")
    tipo = norma.get("tipo")

    relacionamentos = norma.get("relacionamentos")

    source_process = source_by_urn.get(urn)

    # nenhum dos dois existe
    if not relacionamentos and not source_process:

        sem_relacionamento_e_sem_source.append({
            "urn": urn,
            "titulo": norma.get("titulo"),
            "tipo": norma.get("tipo")
        })

# =========================
# RESULTADOS
# =========================
print("Total sem relacionamentos e sem sourceProcess:")
print(len(sem_relacionamento_e_sem_source))
""" print(
    "Normas sem relacionamentos e sem sourceProcess:",
    sem_relacionamento_e_sem_source
) """

with open(
    "data/normas/metadados/normas_sem_proposicao_origem.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        sem_relacionamento_e_sem_source,
        f,
        indent=4,
        ensure_ascii=False
    )