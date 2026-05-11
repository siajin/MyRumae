import logging
import os

from .database import engine
from .models import Base

log = logging.getLogger(__name__)


def init_db():
    if os.environ.get("DROP_AND_RECREATE") == "1":
        Base.metadata.drop_all(bind=engine)
        log.info("기존 테이블 삭제")
    Base.metadata.create_all(bind=engine)
    log.info("DB 생성 완료")


if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    init_db()
