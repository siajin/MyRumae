import os

from .database import engine
from .models import Base


def init_db():
    if os.environ.get("DROP_AND_RECREATE") == "1":
        Base.metadata.drop_all(bind=engine)
        print("기존 테이블 삭제")
    Base.metadata.create_all(bind=engine)
    print("DB 생성 완료")


if __name__ == "__main__":
    init_db()
