
from sqlalchemy import text

from app.db.session import get_engine


def check_connection() -> None:
    engine = get_engine()

    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        print("PostgreSQL connection successful:", result.scalar())


if __name__ == "__main__":
    check_connection()
