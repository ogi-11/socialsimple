from collections.abc import AsyncGenerator
import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime
from fastapi_users.db import SQLAlchemyUserDatabase, SQLAlchemyBaseUserTableUUID
from fastapi import Depends

DATABASE_URL = "sqlite+aiosqlite:///./test.db"

class Base(DeclarativeBase):
    pass
    #this must always be declared since all models must iinherit from Base and SQLAlchemy uses this to build tables.

class User(SQLAlchemyBaseUserTableUUID, Base):
    posts = relationship("Post", back_populates="user")
    #building user table by inheriting from SQLAl... (which is a prebuilt table from FastAPI Users) and Base

class Post(Base):
    __tablename__ = "posts" # corresponds to the posts table in database
    
    """ setup is as follows
    name = Then either Column (which we use if we are storing data), or Relationship (which we use if storing a relationship), then sepcify what you want in that column or whatever 
    """
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4) # primary key, UUID format
    user_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False) # stores the ID of the user who created the post, and nullable is set to false, so it must always exist
    caption = Column(Text) # optional description
    url = Column(String, nullable=False) # where the file is stored
    file_type = Column(String, nullable=False) # image/jepg/...
    file_name = Column(String, nullable=False)#original name
    created_at = Column(DateTime, default=datetime.utcnow) # timestamp of post creation
    
    user = relationship("User", back_populates="posts")
    #we have created a one to many relationship, so one user can basically have many posts


engine = create_async_engine(DATABASE_URL) # this creates tthe database engine, which mannages connections to SQLite
async_session_maker = async_sessionmaker(engine, expire_on_commit=False) #this creates a factory that can produce DB sessions. Every time a request needs DB access, fastpi will call this

async def create_db_and_tables():
    """creating databases and session tables, which starts db engine and creates all session tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    #this opens a db connectrion, calls base.metadata ... and SQLAlch reads models and creates tables if they dont exist
        
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
    # this opens a session, passes it to the endpoint and after the endpoint finishes, it closes the session automatically
    #a database session is a temporary connection to the database, and i need the session to read and write rows, commit transactions and run queries
        
async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)
    #FASTAPI ERS needs an abstraction called a User DB Adapter, because it knows how to insert and retrieve users, hashes passwords and works with our User model.