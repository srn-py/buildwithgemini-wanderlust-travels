# ✈️ Wanderlust Travels — AI Travel Concierge

**Wanderlust Travels** is an agentic AI travel concierge built with the **Google Agent Development Kit (ADK)** and deployed on **Agent Runtime (Vertex AI Reasoning Engine)**. It features an interactive chat interface, rich A2UI card rendering, persistent memory across sessions, live GCP integrations, and multimodal asset generation (images & videos).

---

## 🌟 Architecture & Features

### 🤖 Core Agent Capabilities
- **Persistent Cross-Session Memory**: Integrates **Vertex AI Memory Bank** to automatically remember and recall travel bucket lists, preferred destinations, and user budget preferences across conversations.
- **Rich A2UI Display**: Renders structured UI cards (destinations, itineraries, weather, and media) using **A2UI v0.8 Basic Catalog**.
- **Multimodal Generation**:
  - **Destination Postcards**: Generates high-quality destination images using `gemini-3.1-flash-lite-image` in the `global` region.
  - **Travel Preview Videos**: Generates short video clips using Google's Omni model (`gemini-omni-flash-preview`) in the `global` region via the Interactions API.
- **Dynamic Code Execution**: Uses **Agent Engine Sandbox Code Executor** to safely execute Python code for calculating itemized travel budgets and currency conversions.

---

## ☁️ Google Cloud Services & Integrations

- **Agent Runtime (Vertex AI Reasoning Engine)**: Hosts the agent for scale with Agent-to-Agent (A2A) protocol support.
- **Vertex AI Memory Bank**: Stores long-term user memories and extracts facts after agent turns.
- **Google Cloud Firestore**: NoSQL database for managing the travel destinations catalog (`destinations` collection).
- **Google Cloud Storage**: Public media asset bucket (`wanderlust-travels-media-...`) hosting generated destination postcards and videos.
- **Google Maps APIs**:
  - **Geocoding API**: Converts landmark names and addresses into geographic coordinates.
  - **Places API (New)**: Searches nearby tourist attractions, lodging, and dining options.
- **External Web APIs**: Real-time exchange rates (`open.er-api.com`) and weather forecasts (`open-meteo.com`).

---

## 🛠️ Implemented Agent Tools

| Tool | Description |
| :--- | :--- |
| `search_destinations` | Queries the Firestore travel database by category and budget tier. |
| `add_destination` | Adds new destinations to the Firestore database. |
| `calculate_trip_budget` | Runs Python code inside the Agent Engine Sandbox to compute itemized trip costs. |
| `get_exchange_rates` | Fetches live foreign exchange rates for budget conversions. |
| `geocode_address` | Converts addresses or landmarks into latitude & longitude via Google Maps. |
| `find_nearby_places` | Discovers nearby places of interest using Google Places API (New). |
| `generate_destination_image` | Creates postcard preview images using `gemini-3.1-flash-lite-image`, saves session artifacts, and uploads to public GCS. |
| `generate_destination_video` | Creates preview video clips using `gemini-omni-flash-preview`, saves session artifacts, and uploads to public GCS. |
| `get_weather` | Retrieves weather forecasts for travel locations. |
| `get_current_time` | Looks up local current time across global time zones. |

> **Note on Brief Options**: RAG Engine document retrieval was originally considered in design planning but is not implemented in this repository codebase.

---

## 💻 Local Setup & Execution

### Prerequisites
- Python 3.11+
- `uv` package manager (`pip install uv`)
- Google Cloud SDK (`gcloud`) with active Google Cloud credentials (`gcloud auth application-default login`)

### 1. Install Dependencies
```bash
# In the repository root
uv sync
```

### 2. Set Environment Variables
```bash
export GOOGLE_MAPS_API_KEY="<your_google_maps_api_key>"
export AGENT_ENGINE_RESOURCE_NAME="projects/<project_id>/locations/us-east1/reasoningEngines/<agent_engine_id>"
export AGENT_DIRECTORY="app"
```

### 3. Run the Local Chat Frontend Proxy
```bash
cd frontend
uv run python main.py
```
The FastAPI web server will start locally on port `8080`.

---

## 🚀 Deployment Instructions

### Deploy Agent to Agent Runtime
```bash
agents-cli deploy \
  --update-env-vars GOOGLE_MAPS_API_KEY="<your_google_maps_api_key>" \
  --no-confirm-project
```

### Deploy Frontend Proxy to Cloud Run
```bash
cd frontend
gcloud run deploy wanderlust-travels-frontend \
  --source . \
  --region us-central1 \
  --set-env-vars AGENT_ENGINE_RESOURCE_NAME="projects/<project_id>/locations/us-east1/reasoningEngines/<agent_engine_id>",AGENT_DIRECTORY="app" \
  --allow-unauthenticated
```

---

## 📁 Repository Structure

```
wanderlust-travels/
├── app/
│   ├── agent.py               # Main ADK Agent declaration, prompt, tools & callbacks
│   ├── a2ui_utils.py          # A2UI callback and surface update handlers
│   └── fast_api_app.py        # ADK Web FastAPI entry point
├── frontend/
│   ├── main.py                # FastAPI A2A proxy server
│   └── static/
│       └── index.html         # Ocean Teal themed Chat UI & client-side A2UI renderer
├── agents-cli-manifest.yaml   # agents-cli deployment configuration
└── pyproject.toml             # Python dependencies
```
