import os
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker, Session

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://catalog:catalog123@localhost:5432/catalogdb")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Book(Base):
    __tablename__ = "books"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    author = Column(String, nullable=False)
    isbn = Column(String, unique=True, nullable=False)
    total_copies = Column(Integer, default=1)
    available_copies = Column(Integer, default=1)

Base.metadata.create_all(bind=engine)

class BookIn(BaseModel):
    title: str
    author: str
    isbn: str
    total_copies: int = 1

class StockChange(BaseModel):
    delta: int   # -1 when borrowed, +1 when returned

app = FastAPI(title="Book Catalog Service")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def to_dict(b: Book):
    return {"id": b.id, "title": b.title, "author": b.author, "isbn": b.isbn,
            "total_copies": b.total_copies, "available_copies": b.available_copies}

@app.get("/health")
def health():
    return {"status": "UP", "service": "catalog-service"}

@app.post("/books", status_code=201)
def add_book(data: BookIn, db: Session = Depends(get_db)):
    if db.query(Book).filter(Book.isbn == data.isbn).first():
        raise HTTPException(409, "Book with this ISBN already exists")
    book = Book(**data.model_dump(), available_copies=data.total_copies)
    db.add(book); db.commit(); db.refresh(book)
    return to_dict(book)

@app.get("/books")
def list_books(author: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Book)
    if author:
        q = q.filter(Book.author.ilike(f"%{author}%"))
    return [to_dict(b) for b in q.all()]

@app.get("/books/{book_id}")
def get_book(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    return to_dict(book)

@app.patch("/books/{book_id}/availability")
def change_availability(book_id: int, change: StockChange, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    new_value = book.available_copies + change.delta
    if new_value < 0 or new_value > book.total_copies:
        raise HTTPException(400, "No copies available")
    book.available_copies = new_value
    db.commit(); db.refresh(book)
    return to_dict(book)

@app.delete("/books/{book_id}", status_code=204)
def delete_book(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    db.delete(book); db.commit()