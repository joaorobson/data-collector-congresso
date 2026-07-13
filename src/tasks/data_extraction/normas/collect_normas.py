import json
import requests
from bs4 import BeautifulSoup

tipos = [
    "Decreto Legislativo".replace(" ", "\u00A0"),
    "Emenda Constitucional".replace(" ", "\u00A0"),
    "Lei",
    "Lei Complementar".replace(" ", "\u00A0"),
    "Lei Delegada".replace(" ", "\u00A0"),
    "Medida Provisória".replace(" ", "\u00A0"),
    "Resolução"
]

url_base = "https://www.lexml.gov.br/busca/search"

# 1. Lista que vai guardar todos os documentos de todos os tipos
dados_coletados = []

for tipo in tipos:
    print(f"\n--- Buscando por: {tipo} ---")

    tipo_documento = f"Legislação::{tipo}".replace(" ", "\u00A0")

    start_doc = 1
    max_docs = 50

    while True:

        params = {
            "f6-autoridade": "Federal" if tipo != "Resolução" else "Federal::Legislativo",
            "f7-tipoDocumento": tipo_documento,
            "year": "2010",
            "year-max": "2025",
            "raw": "1",
            "startDoc": start_doc
        }

        try:
            response = requests.get(url_base, params=params)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "xml")

            documentos = soup.find_all("docHit")

            if not documentos:
                print("Fim da paginação.")
                break

            print(f"Página iniciando em {start_doc}: {len(documentos)} docs")

            for doc in documentos:

                meta = doc.find("meta")

                urn = meta.find("urn").text if meta.find("urn") else None
                relacionamentos = meta.find("relacionamentosSucessao").text if meta.find("relacionamentosSucessao") else None
                titulos = meta.find_all("title")
                title = titulos[0].text if titulos else None

                dados_coletados.append({
                    "tipo": tipo.replace("\u00A0", " "),
                    "titulo": title,
                    "urn": urn,
                    "relacionamentos": relacionamentos
                })

            # próxima página
            start_doc += max_docs

        except requests.exceptions.RequestException as e:
            print(f"Erro: {e}")
            break

with open("data/normas/metadados//normas_2010_2025.json", "w", encoding="utf-8") as f:
    json.dump(dados_coletados, f, indent=4, ensure_ascii=False)

print("\nTotal de normas coletadas:", len(dados_coletados))