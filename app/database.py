import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

_raw_url = os.getenv("DATABASE_URL", "")
if not _raw_url:
    raise RuntimeError("Falta la variable de entorno DATABASE_URL")
DATABASE_URL = _raw_url.replace("postgresql://", "postgresql+psycopg://")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,   # verifica la conexion antes de usarla (evita errores por conexiones caidas)
    pool_recycle=1800,    # recicla conexiones cada 30 min (el pooler cierra las inactivas)
    # Supabase usa pgbouncer en modo transaccion: los prepared statements del servidor
    # chocan con el pooler (error DuplicatePreparedStatement). Los desactivamos.
    connect_args={"prepare_threshold": None},
)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
