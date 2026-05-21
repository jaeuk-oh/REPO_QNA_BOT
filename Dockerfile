FROM python:3.11-slim

# chromadb(hnswlib)와 gitpython이 C++ 빌드 도구 필요
RUN apt-get update && apt-get install -y \
    gcc g++ git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# data/ 는 Render Persistent Disk가 마운트되므로 여기서는 빈 디렉토리만 생성
RUN mkdir -p data/repos data/chroma

CMD ["python", "main.py"]
