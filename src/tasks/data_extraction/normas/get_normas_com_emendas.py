import json
import os

INPUTS = [
    "data/camara/metadados/emendas.json",
    "data/senado/metadados/emendas.json",
]

OUTPUT = "data/normas/metadados/normas_com_emendas.json"


def main():

    urns_com_emendas = set()

    for arquivo in INPUTS:

        if not os.path.exists(arquivo):
            print(f"⚠️ Arquivo não encontrado: {arquivo}")
            continue

        with open(arquivo, encoding="utf-8") as f:
            emendas = json.load(f)

        for registro in emendas.values():

            # ignora requisições com erro
            if registro.get("status") != 200:
                continue

            urn = registro.get("urn")
            resultado = registro.get("resultado")

            if not urn:
                continue

            if isinstance(resultado, list) and resultado:
                urns_com_emendas.add(urn)

    urns_com_emendas = sorted(urns_com_emendas)

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(
            urns_com_emendas,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"✅ Total de URNs com pelo menos uma emenda: {len(urns_com_emendas)}")
    print(f"💾 Arquivo salvo em: {OUTPUT}")


if __name__ == "__main__":
    main()