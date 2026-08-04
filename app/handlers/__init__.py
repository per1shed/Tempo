from aiogram import Router

from app.handlers.day import router as day_router
from app.handlers.settings import router as settings_router
from app.handlers.start import router as start_router
from app.handlers.stopwatch import router as stopwatch_router


def setup_routers() -> Router:
    root = Router()
    root.include_router(start_router)
    root.include_router(day_router)
    root.include_router(settings_router)
    root.include_router(stopwatch_router)
    return root
