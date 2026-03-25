# ☀️ Solar Storm Early Warning Network

**TUA Astro Hackathon 2026** — Geomagnetic storm prediction 30–60 minutes ahead using Transformer AI.

## Architecture

```
NOAA SWPC API (1-min)
      │
      ▼
workers/ingest_daemon.py  ─── POST ──►  FastAPI (api/main.py)
                                              │
                                    pipeline/predictor.py
                                              │
                                    SolarTransformer + LoRA
                                              │
                                    SQLite DB + WS broadcast
                                              │
                                    dashboard/app.py (Streamlit)
```

## Quick Start (Local)

### 1. Install dependencies

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment

```bash
copy .env.example .env
# Edit .env if needed (defaults work for local dev)
```

### 3. Train the model (optional — runs in demo/heuristic mode without it)

```bash
python models/train.py --epochs 10 --output checkpoints/solar_lora
```

### 4. Start the API

```bash
# From project root
uvicorn api.main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

### 5. Start the ingestion daemon (new terminal)

```bash
python workers/ingest_daemon.py
```

### 6. Start the dashboard (new terminal)

```bash
streamlit run dashboard/app.py
```

Dashboard: http://localhost:8501

## Docker (all-in-one)

```bash
docker-compose up --build
```

- API: http://localhost:8000
- Dashboard: http://localhost:8501

## Simulate a Storm

**Via the dashboard sidebar** — click "🔴 Simulate CRITICAL Storm"

**Via curl:**

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2026-03-25T12:00:00Z",
    "source": "DSCOVR",
    "bx_gse": 3.2,
    "by_gse": -5.1,
    "bz_gse": -52.0,
    "speed": 950.0,
    "density": 28.5,
    "temperature": 250000.0
  }'
```

## Run Tests

```bash
pytest tests/ -v --tb=short
```

## Project Structure

```
astro-hackathon/
├── api/               # FastAPI backend
│   ├── main.py        # App entrypoint + lifespan
│   ├── ws_manager.py  # WebSocket broadcast manager
│   └── routers/       # ingest, predict, telemetry, ws
├── dashboard/         # Streamlit Time-Lapse AI UI
│   ├── app.py         # Main dashboard
│   └── components/    # gauge, timeseries, heatmap, cone
├── models/            # ML model definitions
│   ├── solar_transformer.py  # 6-layer spatio-temporal Transformer
│   ├── lora_config.py        # PEFT LoRA wrapper
│   ├── autoencoder.py        # VAE for data compression
│   ├── storm_gan.py          # WGAN-GP for storm augmentation
│   ├── surya_loader.py       # HuggingFace Surya → surrogate fallback
│   └── train.py              # Fine-tuning script
├── pipeline/          # Data processing
│   ├── normalizer.py  # Z-score normalisation → torch.Tensor
│   └── predictor.py   # Inference engine + heuristic fallback
├── workers/
│   └── ingest_daemon.py  # NOAA SWPC polling daemon (APScheduler)
├── schemas/           # Pydantic v2 models
│   ├── telemetry.py   # SensorTelemetry (Esquema 1)
│   └── prediction.py  # StormPrediction (Esquema 2)
├── db/                # SQLAlchemy ORM
│   ├── models.py      # TelemetryRecord, PredictionRecord
│   └── database.py    # Async engine + session
├── tests/             # pytest
├── config.py          # Centralised settings (pydantic-settings)
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## AI Model Details

| Component        | Description                                          |
| ---------------- | ---------------------------------------------------- |
| **Base model**   | SolarTransformer (6 layers, 8 heads, d_model=512)    |
| **Fine-tuning**  | LoRA adapters (r=16, α=32) via PEFT                  |
| **Augmentation** | WGAN-GP GAN generates synthetic Kp≥7 storm sequences |
| **Compression**  | VAE latent space for anomaly detection               |
| **Fallback**     | Burton et al. physics heuristic (no GPU required)    |

## Data Sources

| Source           | URL                                                    | Fields                   |
| ---------------- | ------------------------------------------------------ | ------------------------ |
| NOAA SWPC MAG    | `services.swpc.noaa.gov/json/rtsw/rtsw_mag_1m.json`    | Bx, By, Bz               |
| NOAA SWPC Plasma | `services.swpc.noaa.gov/json/rtsw/rtsw_plasma_1m.json` | Speed, Density, Temp     |
| NASA DONKI       | `api.nasa.gov/DONKI`                                   | CME/storm labels         |
| SuryaBench S3    | `s3://nasa-surya-bench/`                               | Historical training data |
