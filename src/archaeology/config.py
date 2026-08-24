import os

DATABASE_URL: str = os.environ.get(
    "ARCHAEOLOGY_DATABASE_URL",
    "postgresql+psycopg://archaeology:archaeology@localhost:5432/archaeology",
)
