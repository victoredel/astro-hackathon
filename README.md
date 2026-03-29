# 🛰️ Astro-Zeka İzleme Platformu (TUA Hackathon)

Bu platform; uzay telemetrisi alımı, güneş fırtınası tahmini ve gerçek zamanlı yörünge etkisi analizi için tasarlanmış kapsamlı bir sistemdir. Uzay hava durumu verilerini işlemek ve potansiyel risklere karşı uyarıda bulunmak için gelişmiş Yapay Zeka modellerini (IBM ve NASA mimarilerine dayalı) kullanır.

## 🏗️ Sistem Mimarisi
Proje, Docker Compose ile orkestre edilen bir mikro hizmet mimarisi üzerine inşa edilmiştir:

*   **API (FastAPI):** Tahminleri yöneten, veritabanı erişimini (SQLite/SQLAlchemy) sağlayan ve WebSockets üzerinden iletişim kuran sistemin çekirdeğidir.
*   **Dashboard (Streamlit):** Veri görselleştirme, güneş telemetrisi ve risk uyarıları için interaktif bir arayüzdür.
*   **Worker (Veri Alım Daemon'ı):** Harici kaynaklardan (NOAA, NASA DONKI) veri tüketen ve veritabanını asenkron olarak besleyen arka plan servisidir.

## 🚀 Temel Özellikler
*   **Yapay Zeka Destekli Güneş Tahmini:** Uzay hava durumu olaylarını 30 dakikalık bir ufukla tahmin etmek için Solar Transformer ve Storm GAN modellerinin uygulanması.
*   **LoRA Adaptasyonu:** Büyük ölçekli temel modelleri (IBM/NASA Surya) belirli telemetri görevlerinde özelleştirmek için düşük dereceli adaptörlerin (LoRA) kullanımı.
*   **Gerçek Zamanlı İzleme:** Zaman serisi görselleştirmeleri, ısı haritaları ve risk göstergeleri içeren kontrol paneli.
*   **Asenkron Veri Alımı:** Ana API'yi engellemeden NOAA ve NASA'dan veri yakalamak için optimize edilmiş daemon.

## 🛠️ Teknoloji Yığını
*   **Dil:** Python 3.10+
*   **Backend:** FastAPI, Uvicorn, Alembic (migrasyonlar).
*   **Frontend:** Streamlit, Plotly, Globe.gl.
*   **IA/ML:** PyTorch, Hugging Face (PEFT/LoRA), NumPy, Pandas.
*   **Veritabanı:** asenkron işlemler için aiosqlite ile SQLite.
*   **Konteynerler:** Docker & Docker Compose.

## ⚙️ Kurulum ve Yapılandırma

### Ön Koşullar
*   Docker ve Docker Compose yüklü olmalıdır.
*   Bir NASA API anahtarı ([buradan alın](https://api.nasa.gov/)).

### Adımlar
1.  **Depoyu klonlayın:**
    ```bash
    git clone https://github.com/victoredel/astro-hackathon.git
    cd astro-hackathon
    ```

2.  **Ortam değişkenlerini yapılandırın:**
    Kök dizinde aşağıdaki içeriğe sahip bir `.env` dosyası oluşturun:
    ```env
    NASA_API_KEY=api_anahtariniz_buraya
    DATABASE_URL=sqlite+aiosqlite:///./data/solar.db
    API_BASE_URL=http://api:8000
    SATNOGS_API_KEY=satnogs_tokeniniz_buraya
    ```

3.  **Docker ile çalıştırın:**
    ```bash
    docker-compose up --build -d
    ```

### Servislere Erişim:
*   **Dashboard:** [http://localhost:8501](http://localhost:8501)
*   **API Dokümantasyonu (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)

## 📂 Proje Yapısı
```plaintext
├── api/                # FastAPI uç noktaları ve iş mantığı
├── dashboard/          # Streamlit kullanıcı arayüzü
│   └── pages/          # Dashboard sayfaları (Yörünge İzleme vb.)
├── models/             # Yapay Zeka mimarileri (Transformers, GANs)
├── pipeline/           # Veri işleme ve çıkarım mantığı
├── db/                 # SQLAlchemy modelleri ve bağlantı
├── workers/            # Veri alım daemon'ları
└── data/               # Yerel veritabanı depolama
```
