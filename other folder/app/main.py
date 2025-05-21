# app/main.py:  fastapi entrypoint: server run + app configuration

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import user_router
from . import models, database

#create database table automatically 
models.Base.metadata.create_all(bind=database.engine)

#fast api application for api control
app = FastAPI()

@app.get("/")
async def root():
    return {"message": "hello from main"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# add /regi /login /me /admin-only /dashboard as part of fastapi
app.include_router(user_router.router, prefix="/auth", tags=["auth"])
