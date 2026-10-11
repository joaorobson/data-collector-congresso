import json
import unicodedata


def normalizar(texto: str) -> str:
    """Remove acentos e converte para minúsculas para comparação segura."""
    if not isinstance(texto, str):
        return ""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).strip().lower()


def filtrar_dados(caminho_entrada: str, caminho_saida: str):
    # 1. Carrega o arquivo JSON
    with open(caminho_entrada, "r", encoding="utf-8") as f:
        dados = json.load(f)

    # 2. Mantém apenas os itens cujo "tipo" NÃO seja "Medida Provisória"
    dados_filtrados = {
        key: item for key, item in dados.items() if "medida.provisoria" not in key
    }

    # 3. Salva a lista filtrada em um novo arquivo
    with open(caminho_saida, "w", encoding="utf-8") as f:
        json.dump(dados_filtrados, f, ensure_ascii=False, indent=4)

    total_removidos = len(dados) - len(dados_filtrados)
    print(f"Total original: {len(dados)}")
    print(f"Itens removidos: {total_removidos}")
    print(f"Itens mantidos: {len(dados_filtrados)}")


if __name__ == "__main__":
    # Substitua pelos nomes dos seus arquivos
    filtrar_dados("data/normas/metadados/fases_tramitacao.json", "data/normas/metadados/dados_filtrados.json")