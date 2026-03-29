# 🛰️ Astro-Intelligence Monitoring Platform (TUA Hackathon)

This platform is a comprehensive system designed for space telemetry ingestion, solar storm prediction, and real-time orbital impact analysis. It uses advanced Artificial Intelligence models (based on IBM and NASA architectures) to process space weather data and alert against potential risks.

## 🏗️ System Architecture
The project is built on a microservices architecture orchestrated with Docker Compose:

*   **API (FastAPI):** The core of the system that manages predictions, database access (SQLite/SQLAlchemy), and communicates via WebSockets.
*   **Dashboard (Streamlit):** An interactive interface for data visualization, solar telemetry, and risk alerts.
*   **Worker (Ingest Daemon):** A background service that consumes data from external sources (NOAA, NASA DONKI) and asynchronously feeds the database.

## 🚀 Key Features
*   **AI-Powered Solar Prediction:** Implementation of Solar Transformer and Storm GAN models to predict space weather events with a 30-minute horizon.
*   **LoRA Adaptation:** Use of Low-Rank Adapters (LoRA) to specialize large-scale base models (IBM/NASA Surya) for specific telemetry tasks.
*   **Real-Time Monitoring:** Dashboard including time-series visualizations, heatmaps, and risk indicators.
*   **Asynchronous Ingestion:** Optimized daemon to capture data from NOAA and NASA without blocking the main API.

## 🛠️ Technology Stack
*   **Language:** Python 3.10+
*   **Backend:** FastAPI, Uvicorn, Alembic (migrations).
*   **Frontend:** Streamlit, Plotly, Globe.gl.
*   **AI/ML:** PyTorch, Hugging Face (PEFT/LoRA), NumPy, Pandas.
*   **Database:** SQLite with aiosqlite for asynchronous operations.
*   **Containers:** Docker & Docker Compose.

## ⚙️ Setup and Configuration

### Prerequisites
*   Docker and Docker Compose must be installed.
*   A NASA API key ([get it here](https://api.nasa.gov/)).

### Steps
1.  **Clone the repository:**
    ```bash
    git clone https://github.com/victoredel/astro-hackathon.git
    cd astro-hackathon
    ```

2.  **Configure environment variables:**
    Create a `.env` file in the root directory with the following content:
    ```env
    NASA_API_KEY=your_api_key_here
    DATABASE_URL=sqlite+aiosqlite:///./data/solar.db
    API_BASE_URL=http://api:8000
    SATNOGS_API_KEY=your_satnogs_token_here
    ```

3.  **Run with Docker:**
    ```bash
    docker-compose up --build -d
    ```

### Access to Services:
*   **Dashboard:** [http://localhost:8501](http://localhost:8501)
*   **API Documentation (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)

## 📂 Project Structure
```plaintext
├── api/                # FastAPI endpoints and business logic
├── dashboard/          # Streamlit user interface
│   └── pages/          # Dashboard pages (Orbital Tracking, etc.)
├── models/             # AI architectures (Transformers, GANs)
├── pipeline/           # Data processing and inference logic
├── db/                 # SQLAlchemy models and connection
├── workers/            # Data ingestion daemons
└── data/               # Local database storage
```
