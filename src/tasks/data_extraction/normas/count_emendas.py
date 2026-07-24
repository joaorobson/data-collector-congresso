import json

with open("data/camara/metadados/emendas.json", encoding="utf-8") as f:
    emendas_camara = json.load(f)

with open("data/senado/metadados/emendas.json", encoding="utf-8") as f:
    emendas_senado = json.load(f)

urns = {}
total_emendas = 0

for base in [emendas_camara, emendas_senado]:
    for proposicao in base.values():
        urn = proposicao.get("urn")
        resultado = proposicao.get("resultado") or []

        if not urn:
            continue

        if urn not in urns:
            urns[urn] = False

        if resultado:
            urns[urn] = True
            total_emendas += len(resultado)

total_urns_com_emendas = sum(urns.values())

print("Total de URNs únicas:", len(urns))
print("Total de URNs com emendas:", total_urns_com_emendas)
print("Total absoluto de emendas:", total_emendas)