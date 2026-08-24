from fastapi import FastAPI

app = FastAPI(title="SentinelSIF API")


@app.get("/health")
def health():
    return {"status": "ok"}
