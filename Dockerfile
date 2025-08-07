FROM python:3.10-slim

WORKDIR /app

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    git gcc libglib2.0-0 libsm6 libxext6 \
    libxrender-dev libgl1-mesa-glx libstdc++6 \
    libopenblas-dev libgomp1 wget curl \
    && rm -rf /var/lib/apt/lists/*

# requirements 복사
COPY requirements.txt .

# pip 업그레이드 + torch/torchvision (GPU + CUDA 11.8) 설치
RUN pip install --upgrade pip setuptools wheel && \
    pip install torch==2.3.0+cu118 torchvision==0.18.0+cu118 --index-url https://download.pytorch.org/whl/cu118 && \
    pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY . .

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
