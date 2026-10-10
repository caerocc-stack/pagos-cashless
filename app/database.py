import os
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

_raw_url = os.getenv("DATABASE_URL", "")
if not _raw_url:
    raise RuntimeError("Falta la variable de entorno DATABASE_URL")
DATABASE_URL = _raw_url.replace("postgresql://", "postgresql+psycopg://")

# Supabase usa pgbouncer en modo transaccion: los prepared statements del servidor
# chocan con el pooler (error DuplicatePreparedStatement). Los desactivamos.
_connect_args = {} if DATABASE_URL.startswith("sqlite") else {"prepare_threshold": None}

if os.getenv("VERCEL"):
    # En Vercel las instancias se congelan entre pedidos: un pool propio dejaria
    # conexiones colgadas. El pooler de Supabase (puerto 6543) ya hace de pool.
    engine = create_engine(DATABASE_URL, poolclass=NullPool, connect_args=_connect_args)
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,   # verifica la conexion antes de usarla (evita errores por conexiones caidas)
        pool_recycle=1800,    # recicla conexiones cada 30 min (el pooler cierra las inactivas)
        connect_args=_connect_args,
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
