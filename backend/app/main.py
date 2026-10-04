from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.database import close_mongodb_connection, connect_to_mongodb, init_db_indexes
from app.logging import logger, setup_logging
from app.modules.ai_waiter.router import router as ai_waiter_router
from app.modules.auth_tenancy.router import router as auth_router
from app.modules.bills.router import router as bills_router
from app.modules.cafes.router import router as cafes_router
from app.modules.cart.router import router as cart_router
from app.modules.menu.router import router as menu_router
from app.modules.orders.router import router as orders_router
from app.modules.realtime.router import router as realtime_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(debug=settings.DEBUG)
    logger.info("Starting up Cafe AI Waiter Backend")
    db = await connect_to_mongodb()
    await init_db_indexes(db)
    yield
    logger.info("Shutting down Cafe AI Waiter Backend")
    await close_mongodb_connection()


app = FastAPI(
    title="Cafe AI Waiter Ordering Service API",
    description="Multi-tenant B2B QR and AI Waiter ordering service for local cafes in India",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for mobile web and staff dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production via config
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please try again later."},
    )


# Health and Readiness
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "service": "cafe-ai-waiter"}


@app.get("/ready", tags=["Health"])
async def readiness_check():
    return {"status": "ready"}


# Register API routers
app.include_router(auth_router)
app.include_router(cafes_router)
app.include_router(menu_router)
app.include_router(cart_router)
app.include_router(orders_router)
app.include_router(bills_router)
app.include_router(ai_waiter_router)
app.include_router(realtime_router)
