from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import dispose_engine
from routes import auth, api
from routes.video import router as video_router
from routes.weather import router as weather_router
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from routes.media import router as media_router


MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)




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
app.include_router(video_router)
app.include_router(weather_router)

app.include_router(media_router, prefix="/api")

app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

@app.on_event("shutdown")
async def shutdown_event():
    await dispose_engine()


@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok"}