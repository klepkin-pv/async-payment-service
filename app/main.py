from fastapi import FastAPI

app = FastAPI(title="Async Payment Service")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
