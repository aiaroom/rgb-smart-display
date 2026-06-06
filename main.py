from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import dispose_engine
from routes import auth, api


app = FastAPI(
    title="RGB Smart Display API",
    description="Backend для панели УК и клиентских дисплеев ЖК",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://10.8.0.11:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(api.router, prefix="/api", tags=["API"])


@app.on_event("shutdown")
async def shutdown_event():
    await dispose_engine()


@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok"}