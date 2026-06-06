from fastapi import FastAPI

from database import dispose_engine
from routes import auth


app = FastAPI(title="RGB Smart Display")

app.include_router(auth.router)


@app.on_event("shutdown")
async def shutdown_event():
    await dispose_engine()


@app.get("/")
async def root():
    return {"status": "ok"}