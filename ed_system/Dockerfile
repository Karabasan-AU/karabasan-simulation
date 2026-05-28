FROM python:3.10-slim

WORKDIR /app

# Gerekli sistem kütüphanelerini kur
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY ed_system/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kaynak kodları ana dizine göre kopyalıyoruz
COPY ed_system/src/ ./src/
COPY shared/ ./shared/

# Yönlendiriciyi başlat
CMD ["python", "src/main.py"]