from fastapi import FastAPI
from services.user.router import user_service_router


app = FastAPI(title="Meno")

app.include_router(user_service_router)
