import asyncio
import aiohttp
import logging
from typing import List, Any
from tqdm.asyncio import tqdm

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


class AsyncCollector:
    def __init__(self, max_concurrent: int = 10, retries: int = 5, timeout: int = 60):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.retries = retries
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    async def fetch(self, session: aiohttp.ClientSession, url: str) -> dict:
        async with self.semaphore:
            ultimo_erro = None

            for attempt in range(self.retries):
                try:
                    async with session.get(url, timeout=self.timeout) as response:

                        content_type = response.headers.get("Content-Type", "")

                        if response.status == 200:
                            if "application/json" in content_type:
                                body = await response.json()
                            else:
                                body = await response.text()

                            return {
                                "status": 200,
                                "erro": None,
                                "resultado": body
                            }

                        if response.status == 429:
                            wait = int(response.headers.get("Retry-After", 2 ** attempt))
                            logging.warning(f"[429] {url} - aguardando {wait}s")
                            await asyncio.sleep(wait)
                            continue

                        texto = await response.text()

                        return {
                            "status": response.status,
                            "erro": texto,
                            "resultado": []
                        }

                except Exception as e:
                    ultimo_erro = str(e)
                    wait = 2 ** attempt
                    logging.error(f"[Erro] {url} ({attempt+1}/{self.retries}) {e}")
                    await asyncio.sleep(wait)

            return {
                "status": None,
                "erro": ultimo_erro,
                "resultado": []
            }

    async def _fetch_and_store(
        self,
        session,
        url,
        index,
        results
    ):
        results[index] = await self.fetch(session, url)

    async def collect(self, urls: List[str]) -> List[Any]:
        results = [None] * len(urls)

        async with aiohttp.ClientSession(
            headers={
                "User-Agent": "BotLegislativo/1.0",
                "Accept": "application/json",
            }
        ) as session:

            tasks = [
                self._fetch_and_store(session, url, i, results)
                for i, url in enumerate(urls)
            ]

            await tqdm.gather(*tasks, desc="Coletando")

        return results