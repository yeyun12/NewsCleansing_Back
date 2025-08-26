# app/config.py
import os
from dotenv import load_dotenv

# .env 로드 (이 모듈이 임포트될 때 즉시)
load_dotenv()

class Settings:
    # 팀원(추천) 서버 베이스 URL
    EXTERNAL_API_BASE_URL: str = os.getenv("EXTERNAL_API_BASE_URL", "").rstrip("/")
    # (선택) 추천 호출 타임아웃(초)
    RECO_API_TIMEOUT: float = float(os.getenv("RECO_API_TIMEOUT", "8"))

settings = Settings()
