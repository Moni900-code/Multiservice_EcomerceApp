# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL) #for db connetion
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) #session creation for each db access
Base = declarative_base() #base class for orm(object relational mapper) model(help for table creation)
