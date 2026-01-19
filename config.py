import os
from datetime import timedelta

class Config:
    # ======================
    # BASIC
    # ======================
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ======================
    # MYSQL (Railway)
    # ======================
    MYSQL_USER = os.getenv("MYSQLUSER")
    MYSQL_PASSWORD = os.getenv("MYSQLPASSWORD")
    MYSQL_HOST = os.getenv("MYSQLHOST")
    MYSQL_PORT = os.getenv("MYSQLPORT", "3306")
    MYSQL_DB = os.getenv("MYSQLDATABASE")

    # ======================
    # DATABASE URI BUILDER
    # ======================
    @classmethod
    def is_mysql_ready(cls) -> bool:
        return all([
            cls.MYSQL_USER,
            cls.MYSQL_PASSWORD,
            cls.MYSQL_HOST,
            cls.MYSQL_DB,
        ])

    @classmethod
    def build_database_uri(cls) -> str:
        if cls.is_mysql_ready():
            return (
                f"mysql+mysqlconnector://"
                f"{cls.MYSQL_USER}:{cls.MYSQL_PASSWORD}"
                f"@{cls.MYSQL_HOST}:{cls.MYSQL_PORT}"
                f"/{cls.MYSQL_DB}"
            )

        # ✅ FALLBACK SQLITE (WAJIB ADA)
        return "sqlite:///attendance.db"

    SQLALCHEMY_DATABASE_URI = build_database_uri.__func__(None)

    # ======================
    # SESSION & UPLOAD
    # ======================
    UPLOAD_FOLDER = "static/uploads"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    @staticmethod
    def init_app(app):
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
print("MYSQL ENV:", {
    "host": os.getenv("MYSQLHOST"),
    "db": os.getenv("MYSQLDATABASE")
})
