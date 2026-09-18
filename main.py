import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from app.database import init_db
from app.crawler import crawler
from app.routes import router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("leetcode_collector")

templates = Jinja2Templates(directory="templates")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database and Seed Users
    logger.info("[STARTUP] Initializing SQLite database...")
    init_db()
    logger.info("[STARTUP] Initializing persistent CSV cache & database...")
    crawler.initialize_cache()
    logger.info("[STARTUP] Collector ready.")
    yield
    # Shutdown
    if crawler.is_running:
        logger.info("[SHUTDOWN] Stopping crawler...")
        crawler.stop()

app = FastAPI(
    title="LeetCode Profile Collector",
    description="Public LeetCode profile discovery and statistics collector for MNNIT students",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API endpoints
app.include_router(router)

@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
async def index_page(request: Request):
    """Serve the primary dashboard interface."""
    return templates.TemplateResponse(request=request, name="users.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)
