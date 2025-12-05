from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Depends
from app.schemas import PostCreate, PostResponse, UserRead, UserCreate, UserUpdate
from app.db import Post, create_db_and_tables, get_async_session, User
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from sqlalchemy import select
from app.images import imagekit
from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
import shutil
import os
import uuid
import tempfile
from app.users import auth_backend, current_active_user, fastapi_users

@asynccontextmanager #turns function in async context manager, which basically says to do something before and after the block runs.
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield
    #basically means that when FastAPI starts, run the create_db... and when it stops, run whatever comes after yield


app = FastAPI(lifespan=lifespan) # tells fastapi use this function to run startup and shutdown logic

#these are all using fastapi users, which is a library that gives ready made auth, reg, pass reset, email ver and user CRUD routes\
#app.include_router(...) this basically says - add this group of endpoints to my fastapi app
app.include_router(fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]) #handles login and logout and returns JWT access tokens, basically adds endpoints like /auth/jwt/login
app.include_router(fastapi_users.get_register_router(UserRead, UserCreate), prefix="/auth", tags=["auth"]) #adds /auth/register. users can sign up and it returns UserRead
app.include_router(fastapi_users.get_reset_password_router(), prefix="/auth", tags=["auth"]) # allows password recovery via email based reset tokens. so /auth/sorgot-password sends reset token and /asuth/reset-password resets the user password
app.include_router(fastapi_users.get_verify_router(UserRead), prefix="/auth", tags=["auth"]) # purpose is for email verification, usually after registration
app.include_router(fastapi_users.get_users_router(UserRead, UserUpdate), prefix="/users", tags=["users"]) #allows logged in users to manage their profile and admins to manage all users

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    caption: str = Form(""),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
    # defined a POST API endpoint that: accepts an uploaded file, accepts a text caption, requires the user to be logged in, uses a db session, performs async logic
):
    temp_file_path = None
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            temp_file_path = temp_file.name
            shutil.copyfileobj(file.file, temp_file)
            #creates a temp file and stores the path so i can later open, upload and delete it
            #lastly, it copies the uploaded frile from FastAPI into the temporary file
        
        upload_result = imagekit.upload_file(
            file=open(temp_file_path, "rb"),
            file_name=file.filename,
            options = UploadFileRequestOptions(
                use_unique_file_name=True,
                tags=["backend_upload"]
            )
        )
        
        if upload_result.response_metadata.http_status_code == 200:
            post = Post(
                user_id=user.id,
                caption=caption,
                url=upload_result.url,
                file_type='video' if file.content_type.startswith("video/") else "image",
                file_name=upload_result.name
            )
            session.add(post)
            await session.commit()
            await session.refresh(post)
            return post
            #this creates a post in the database. Post(..) creates a new Post object, session.add(post) stages it, commit writes it to db, refresh gets the ID from db and return returns to client
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        file.file.close()
    
@app.get("/feed")
async def get_feed(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user)
):
    result = await session.execute(select(Post).order_by(Post.created_at.desc()))
    posts = [row[0] for row in result.all()]
    
    result = await session.execute(select(User))
    users = [row[0] for row in result.all()]
    user_dict = {u.id: u.email for u in users}
    
    
    posts_data = []
    for post in posts:
        posts_data.append(
            {
                "id" : str(post.id),
                "user_id": str(post.user_id),
                "caption": post.caption,
                "url" : post.url,
                "file_type" : post.file_type,
                "file_name" : post.file_name,
                "created_at" : post.created_at.isoformat(),
                "is_owner": post.user_id == user.id,
                "email": user_dict.get(post.user_id, "Unknown")
            }
        )
        
    return {"posts": posts_data}

@app.delete("/posts/{post_id}")
async def delete_post(post_id: str, session: AsyncSession = Depends(get_async_session), user: User = Depends(current_active_user)):
    try:
        post_uuid = uuid.UUID(post_id)
        #what is uuid?
        
        result = await session.execute(select(Post).where(Post.id == post_uuid))
        post = result.scalars().first() #this returns exact result
        
        if not post:
            raise HTTPException(status_code=404, detail = "Post not found")
        
        if post.user_id != user.id:
            raise HTTPException(status_code=403, detail = "You don't have permission to delete this post.")
        
        await session.delete(post)
        await session.commit()
        
        return {"success": True, "message": "Post deleted successfully"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail = str(e))