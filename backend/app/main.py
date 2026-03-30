from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes.debug import router as debug_router
from app.routes.health import router as health_router
from app.routes.plants import router as plants_router
from app.routes.regions import router as regions_router
from app.routes.stats import router as stats_router
from app.routes.query import router as query_router

app = FastAPI(title="Stranded Asset Early Warning API")

_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(debug_router)
app.include_router(plants_router)
app.include_router(regions_router)
app.include_router(stats_router)
app.include_router(query_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "stranded-asset-warning", "docs": "/docs"}
