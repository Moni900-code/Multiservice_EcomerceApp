from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer
from app.auth import decode_token, get_current_user
from .. import schemas, crud, database, auth
from app.auth import decode_token

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/register", response_model=schemas.UserResponse)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db=db, user=user)

@router.post("/login")
def login(user: schemas.UserLogin, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, user.email)
    if not db_user or not auth.verify_password(user.password, db_user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = auth.create_access_token(data={"sub": db_user.email, "role": db_user.role})
    return {"access_token": token, "token_type": "bearer"}

@router.get("/admin-only")
def read_admin_data(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    return {"message": "Welcome Admin!"}

@router.get("/me")
def read_my_data(current_user: dict = Depends(get_current_user)):
    return {"email": current_user["sub"], "role": current_user["role"]}

@router.get("/dashboard")
def dashboard(current_user: dict = Depends(get_current_user)):
    if current_user["role"] == "admin":
        return {"message": "Welcome Admin!"}
    elif current_user["role"] == "user":
        return {"message": "Welcome User!"}
    else:
        raise HTTPException(status_code=403, detail="Unknown role")
    
def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = decode_token(token)
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token or expired token")
