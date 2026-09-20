import httpx


async def notify(url, message):
    if not url: return False
    async with httpx.AsyncClient(timeout=5) as client:
        response=await client.post(url,json={"content":message,"text":message}); response.raise_for_status()
    return True
