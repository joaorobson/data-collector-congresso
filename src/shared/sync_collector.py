import json
import requests

class SyncCollector:

    def collect(self, url: str, headers: dict = {'Accept': 'application/json', 'User-Agent': 'MyCollectorScript/1.0'}) -> dict:
        try:
            data = requests.get(url, headers=headers)
        except Exception as e:
            print(f"Erro: {e}")

        return data.json()

    def store_data(self, data: dict, filepath: str) -> None:
        json.dump(data, open(filepath, "w"))
