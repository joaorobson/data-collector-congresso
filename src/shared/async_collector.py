import asyncio
import aiohttp
import json
import logging
from typing import List, Optional, Any, Tuple
from tqdm.asyncio import tqdm

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

class AsyncCollector:
    def __init__(self, max_concurrent: int = 10, retries: int = 5, timeout: int = 60):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.retries = retries
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    async def fetch(self, session: aiohttp.ClientSession, url: str) -> Optional[dict]:
        async with self.semaphore:
            for attempt in range(self.retries):
                try:
                    async with session.get(url, timeout=self.timeout) as response:
                        if response.status == 200:
                            content_type = response.headers.get("Content-Type", "")

                            if "application/json" in content_type:
                                return await response.json()

                            # fallback: XML ou texto
                            return await response.text()
                        if response.status == 429:
                            wait = int(response.headers.get("Retry-After", 2 ** attempt))
                            logging.warning(f"[429] {url} – aguardando {wait}s...")
                            await asyncio.sleep(wait)
                            continue
                        logging.error(f"[{response.status}] {url}")
                        return None
                except Exception as e:
                    wait = 2 ** attempt
                    logging.error(f"[Erro] {url} (tentativa {attempt + 1}/{self.retries}): {e}")
                    await asyncio.sleep(wait)
            return None

    async def _fetch_and_store(self, session: aiohttp.ClientSession, url: str, index: int, results: List[Any]) -> Optional[Tuple[int, str]]:
        result = await self.fetch(session, url)
        if result is not None:
            results[index] = result # Armazena o JSON bruto
            return None
        return (index, url)

    async def collect(self, urls: List[str]) -> List[Any]:
        results: List[Any] = [None] * len(urls)
        async with aiohttp.ClientSession(
            headers={"User-Agent": "BotLegislativo/1.0", "Accept": "application/json"}
        ) as session:
            tasks = [self._fetch_and_store(session, url, i, results) for i, url in enumerate(urls)]
            failed_results = await tqdm.gather(*tasks, desc="Coletando")
            
            failed = [res for res in failed_results if res is not None]
            if failed:
                logging.info(f"🔁 Tentando novamente {len(failed)} falhas...")
                retry_tasks = [self._fetch_and_store(session, url, i, results) for i, url in failed]
                await tqdm.gather(*retry_tasks, desc="Retrying")
        return results