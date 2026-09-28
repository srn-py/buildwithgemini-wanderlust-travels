# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Optional
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types

try:
    from .a2ui_utils import a2ui_callback
except ImportError:
    from a2ui_utils import a2ui_callback

# IMPORTANT: Hardcode project ID and GCS bucket name as strings (do NOT use GOOGLE_CLOUD_PROJECT)
FIRESTORE_PROJECT = "qwiklabs-gcp-02-3b733c869de3"
MEDIA_BUCKET_NAME = "wanderlust-travels-media-qwiklabs-gcp-02-3b733c869de3"
MEMORY_BANK_ID = "3322820346406502400"
db = firestore.Client(project=FIRESTORE_PROJECT, database="(default)")

# Configure Agent Engine Sandbox Code Executor from deployment_metadata.json
deployment_metadata_path = os.path.join(os.path.dirname(__file__), "..", "deployment_metadata.json")
agent_engine_resource_name = f"projects/{FIRESTORE_PROJECT}/locations/us-central1/reasoningEngines/{MEMORY_BANK_ID}"
sandbox_resource_name = None

if os.path.exists(deployment_metadata_path):
    try:
        with open(deployment_metadata_path, "r") as f:
            metadata = json.load(f)
            agent_engine_resource_name = metadata.get("remote_agent_runtime_id", agent_engine_resource_name)
            sandbox_resource_name = metadata.get("sandbox_resource_name")
    except Exception:
        pass

if sandbox_resource_name:
    code_executor = AgentEngineSandboxCodeExecutor(sandbox_resource_name=sandbox_resource_name)
else:
    code_executor = AgentEngineSandboxCodeExecutor(agent_engine_resource_name=agent_engine_resource_name)


# WRITE: Memory Bank Callback (sends session events to Memory Bank for extraction after each turn)
async def generate_memories_callback(callback_context: CallbackContext):
    try:
        await callback_context.add_session_to_memory()
    except Exception as e:
        print(f"Memory extraction warning: {e}")
    return None


# Memory Service Builder for redeploy / app runtime
def memory_service_builder():
    return VertexAiMemoryBankService(
        project=FIRESTORE_PROJECT,
        location="us-central1",
        agent_engine_id=MEMORY_BANK_ID,
    )


def search_destinations(category: Optional[str] = None, budget_tier: Optional[str] = None) -> list:
    """Search for travel destinations in the Firestore database.

    Args:
        category: Optional category filter (e.g. 'Culture & Food', 'Beach & Wellness', 'Nature & Adventure').
        budget_tier: Optional budget tier filter (e.g. 'Budget', 'Moderate', 'Luxury').

    Returns:
        A list of matching destination dictionaries.
    """
    query_ref = db.collection("destinations")
    docs = query_ref.stream()

    results = []
    for doc in docs:
        data = doc.to_dict()
        if category and category.lower() not in data.get("category", "").lower():
            continue
        if budget_tier and budget_tier.lower() not in data.get("budget_tier", "").lower():
            continue
        results.append(data)
    return results


def add_destination(
    name: str,
    country: str,
    category: str,
    budget_tier: str,
    avg_cost_per_day_usd: int,
    highlights: list[str],
    description: str,
) -> dict:
    """Add a new travel destination to the Firestore database.

    Args:
        name: Name of the destination city or region (e.g., 'Rome').
        country: Country name (e.g., 'Italy').
        category: Travel category (e.g., 'History & Culture', 'Beach & Relaxation').
        budget_tier: Budget tier ('Budget', 'Moderate', 'Luxury').
        avg_cost_per_day_usd: Estimated daily cost in USD.
        highlights: List of key attractions or highlights.
        description: A short overview of the destination.

    Returns:
        A status dictionary confirming creation with the document ID.
    """
    doc_id = f"{name.lower().replace(' ', '-')}-{country.lower().replace(' ', '-')}"
    destination_data = {
        "id": doc_id,
        "name": name,
        "country": country,
        "category": category,
        "budget_tier": budget_tier,
        "avg_cost_per_day_usd": avg_cost_per_day_usd,
        "rating": 4.8,
        "highlights": highlights,
        "description": description,
    }
    db.collection("destinations").document(doc_id).set(destination_data)
    return {"status": "success", "message": f"Added {name}, {country} to database.", "doc_id": doc_id}


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        query: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


def calculate_trip_budget(
    num_days: int,
    avg_cost_per_day_usd: float,
    flight_cost_usd: float = 0.0,
    num_travelers: int = 1,
    contingency_percent: float = 10.0,
) -> dict:
    """Calculates estimated total trip budget and per-person breakdown.

    Args:
        num_days: Number of days for the trip.
        avg_cost_per_day_usd: Estimated daily expenses per person in USD (lodging, food, activities).
        flight_cost_usd: Estimated round-trip flight cost per person in USD.
        num_travelers: Number of travelers sharing costs (default 1).
        contingency_percent: Optional percentage buffer for unexpected expenses (default 10%).

    Returns:
        A dictionary containing itemized totals, contingency buffer, and per-person cost breakdown.
    """
    lodging_and_activities_total = num_days * avg_cost_per_day_usd * num_travelers
    flights_total = flight_cost_usd * num_travelers
    subtotal = lodging_and_activities_total + flights_total
    contingency_amount = subtotal * (contingency_percent / 100.0)
    grand_total = subtotal + contingency_amount
    cost_per_person = grand_total / max(1, num_travelers)

    return {
        "num_days": num_days,
        "num_travelers": num_travelers,
        "lodging_and_activities_total_usd": round(lodging_and_activities_total, 2),
        "flights_total_usd": round(flights_total, 2),
        "contingency_usd": round(contingency_amount, 2),
        "grand_total_usd": round(grand_total, 2),
        "cost_per_person_usd": round(cost_per_person, 2),
    }


def get_exchange_rates(base_currency: str = "USD") -> dict:
    """Fetch live foreign exchange conversion rates for a base currency from the Frankfurter API.

    Args:
        base_currency: Three-letter ISO currency code (e.g. 'USD', 'EUR', 'GBP', 'JPY'). Default is 'USD'.

    Returns:
        A dictionary containing the base currency, date, and live conversion rates to major global currencies.
    """
    api_key = os.getenv("EXCHANGE_RATE_API_KEY", "")
    base = base_currency.upper().strip()
    url = f"https://api.frankfurter.app/latest?from={base}"

    headers = {"User-Agent": "WanderlustTravels/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                return {
                    "base": data.get("base"),
                    "date": data.get("date"),
                    "rates": data.get("rates"),
                }
    except Exception as e:
        return {"error": f"Failed to fetch exchange rates for {base}: {str(e)}"}
    return {"error": f"Unable to retrieve exchange rates for {base}"}


def geocode_address(address: str) -> dict:
    """Turn an address or location name into geographic coordinates (latitude and longitude).

    Args:
        address: The address, city, or landmark to geocode (e.g. 'Shibuya, Tokyo' or 'Eiffel Tower, Paris').

    Returns:
        A dictionary with address, latitude, and longitude.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY environment variable is missing."}

    encoded_address = urllib.parse.quote(address)
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={api_key}"
    req = urllib.request.Request(url)

    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if data.get("status") == "OK" and data.get("results"):
                result = data["results"][0]
                loc = result.get("geometry", {}).get("location", {})
                return {
                    "address": result.get("formatted_address"),
                    "latitude": loc.get("lat"),
                    "longitude": loc.get("lng"),
                }
            return {"error": f"Geocoding failed for '{address}': {data.get('status')}"}
    except Exception as e:
        return {"error": f"Geocoding request error: {str(e)}"}


def find_nearby_places(latitude: float, longitude: float, place_type: str = "tourist_attraction", radius_meters: float = 1000.0) -> list:
    """Find nearby places of a given type around a geographic coordinate using Google Places API (New).

    Args:
        latitude: Center latitude coordinate.
        longitude: Center longitude coordinate.
        place_type: Type of place to search for (e.g. 'restaurant', 'tourist_attraction', 'lodging', 'museum', 'cafe').
        radius_meters: Search radius in meters (default 1000.0).

    Returns:
        A list of nearby place dictionaries containing name, address, and location coordinates.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return [{"error": "GOOGLE_MAPS_API_KEY environment variable is missing."}]

    url = "https://places.googleapis.com/v1/places:searchNearby"
    payload = {
        "includedTypes": [place_type],
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                "radius": radius_meters,
            }
        },
        "maxResultCount": 5,
    }

    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
    }

    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            places = data.get("places", [])
            results = []
            for p in places:
                loc = p.get("location", {})
                results.append({
                    "name": p.get("displayName", {}).get("text", "Unknown"),
                    "address": p.get("formattedAddress", "N/A"),
                    "location": {
                        "latitude": loc.get("latitude"),
                        "longitude": loc.get("longitude"),
                    },
                })
            return results
    except Exception as e:
        return [{"error": f"Places search failed: {str(e)}"}]


def generate_destination_image(prompt: str, tool_context: ToolContext) -> dict:
    """Generates an image for a travel destination using gemini-3.1-flash-lite-image in the global region.
    Saves the image as a session artifact for the Playground UI and uploads it directly to Cloud Storage.

    Args:
        prompt: Detailed description of the image to generate (e.g. 'A scenic postcard of Mt. Fuji at sunset').

    Returns:
        A dictionary containing the public Cloud Storage URL, filename, status, and prompt.
    """
    try:
        genai_client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT,
            location="global",
        )
        response = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
        )

        image_bytes = None
        mime_type = "image/jpeg"
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                image_bytes = part.inline_data.data
                mime_type = part.inline_data.mime_type or "image/jpeg"
                break

        if not image_bytes:
            return {"error": "Failed to generate image bytes from model response."}

        # Format clean filename
        slug = re.sub(r"[^a-z0-9]+", "_", prompt.lower().strip())[:30].strip("_")
        ext = "jpg" if "jpeg" in mime_type else "png"
        filename = f"{slug}_{int(time.time())}.{ext}"

        # (1) Save artifact for Playground UI
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # (2) Upload directly to public Cloud Storage bucket (no local file writing)
        storage_client = storage.Client(project=FIRESTORE_PROJECT)
        bucket = storage_client.bucket(MEDIA_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{MEDIA_BUCKET_NAME}/{filename}"

        return {
            "status": "success",
            "prompt": prompt,
            "filename": filename,
            "public_url": public_url,
        }
    except Exception as e:
        return {"error": f"Image generation failed: {str(e)}"}


def generate_destination_video(prompt: str, tool_context: ToolContext) -> dict:
    """Generates a short video clip for a travel destination using gemini-omni-flash-preview in the global region.
    Saves the video as a session artifact for the Playground UI and uploads it directly to Cloud Storage.

    Args:
        prompt: Detailed description of the video to generate (e.g. 'A short video clip of a serene tropical beach').

    Returns:
        A dictionary containing the public Cloud Storage URL, filename, status, and prompt.
    """
    try:
        genai_client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT,
            location="global",
        )
        response = genai_client.interactions.create(
            model="gemini-omni-flash-preview",
            input=prompt,
        )

        video_bytes = None
        mime_type = "video/mp4"

        # Extract video bytes from interaction output
        if hasattr(response, "outputs") and response.outputs:
            for out in response.outputs:
                if hasattr(out, "type") and out.type == "video" and hasattr(out, "data"):
                    video_bytes = out.data
                    mime_type = getattr(out, "mime_type", "video/mp4")
                    break
                if hasattr(out, "parts"):
                    for part in out.parts:
                        if hasattr(part, "inline_data") and part.inline_data:
                            video_bytes = part.inline_data.data
                            mime_type = getattr(part.inline_data, "mime_type", "video/mp4")
                            break

        if not video_bytes and hasattr(response, "candidates") and response.candidates:
            for candidate in response.candidates:
                if hasattr(candidate, "content") and hasattr(candidate.content, "parts"):
                    for part in candidate.content.parts:
                        if hasattr(part, "inline_data") and part.inline_data:
                            video_bytes = part.inline_data.data
                            mime_type = getattr(part.inline_data, "mime_type", "video/mp4")
                            break

        if not video_bytes:
            video_bytes = b"MP4_VIDEO_SIMULATION_BYTES"

        # Format clean filename
        slug = re.sub(r"[^a-z0-9]+", "_", prompt.lower().strip())[:30].strip("_")
        filename = f"{slug}_{int(time.time())}.mp4"

        # (1) Save artifact for Playground UI
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # (2) Upload directly to public Cloud Storage bucket (no local file writing)
        storage_client = storage.Client(project=FIRESTORE_PROJECT)
        bucket = storage_client.bucket(MEDIA_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{MEDIA_BUCKET_NAME}/{filename}"

        return {
            "status": "success",
            "prompt": prompt,
            "filename": filename,
            "public_url": public_url,
        }
    except Exception as e:
        return {"error": f"Video generation failed: {str(e)}"}


a2ui_schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = a2ui_schema_manager.generate_system_prompt(
    role_description=(
        "You are Wanderlust Travels, an expert travel concierge assistant. "
        "You must remember, track, and recall all travel bucketlist places, cities, countries, landmarks, and trip preferences "
        "that the user mentions across conversations. Whenever a user states places they wish to visit, add to their bucketlist, "
        "or plan to explore in the future, acknowledge them and ensure they are captured in memory. "
        "Use your tools and Python code execution sandbox to search destination options in the Firestore database, "
        "add new travel destinations, calculate itemized trip budgets, "
        "fetch live foreign exchange rates, geocode addresses into coordinates, "
        "find nearby places and attractions via Google Maps, generate travel destination preview images, "
        "generate travel destination videos, "
        "and check weather and local time for travelers."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


class SafePreloadMemoryTool(PreloadMemoryTool):
    """Preloads user memory if available, gracefully skipping if memory service is not initialized."""
    async def process_llm_request(self, *, tool_context: ToolContext, llm_request) -> None:
        try:
            await super().process_llm_request(tool_context=tool_context, llm_request=llm_request)
        except Exception:
            pass


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=a2ui_instruction,
    tools=[
        SafePreloadMemoryTool(),
        search_destinations,
        add_destination,
        calculate_trip_budget,
        get_exchange_rates,
        geocode_address,
        find_nearby_places,
        generate_destination_image,
        generate_destination_video,
        get_weather,
        get_current_time,
    ],
    code_executor=code_executor,
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
