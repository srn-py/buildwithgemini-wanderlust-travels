"""
Seed script to populate Firestore with sample travel destinations for Wanderlust Travels.
"""

from google.cloud import firestore

# IMPORTANT: Hardcode project ID as a string to avoid project number issues on Agent Platform.
PROJECT_ID = "qwiklabs-gcp-02-3b733c869de3"
COLLECTION_NAME = "destinations"

DESTINATIONS = [
    {
        "id": "tokyo-japan",
        "name": "Tokyo",
        "country": "Japan",
        "category": "Culture & Food",
        "budget_tier": "Moderate",
        "rating": 4.9,
        "avg_cost_per_day_usd": 150,
        "highlights": ["Shibuya Crossing", "Tsukiji Outer Market", "Meiji Shrine", "Akihabara"],
        "description": "A bustling metropolis blending ultra-modern skyscrapers with historic temples and world-class culinary experiences."
    },
    {
        "id": "kyoto-japan",
        "name": "Kyoto",
        "country": "Japan",
        "category": "Culture & Nature",
        "budget_tier": "Moderate",
        "rating": 4.8,
        "avg_cost_per_day_usd": 130,
        "highlights": ["Fushimi Inari Shrine", "Arashiyama Bamboo Grove", "Kinkaku-ji Golden Pavilion"],
        "description": "Japan's cultural heart filled with classical Buddhist temples, gardens, imperial palaces, and traditional wooden houses."
    },
    {
        "id": "paris-france",
        "name": "Paris",
        "country": "France",
        "category": "Arts & Romance",
        "budget_tier": "Luxury",
        "rating": 4.7,
        "avg_cost_per_day_usd": 220,
        "highlights": ["Eiffel Tower", "Louvre Museum", "Montmartre", "Seine River Cruise"],
        "description": "The global center of art, fashion, gastronomy, and culture with iconic landmarks and romantic café culture."
    },
    {
        "id": "bali-indonesia",
        "name": "Bali",
        "country": "Indonesia",
        "category": "Beach & Wellness",
        "budget_tier": "Budget",
        "rating": 4.8,
        "avg_cost_per_day_usd": 65,
        "highlights": ["Ubud Monkey Forest", "Tegallalang Rice Terraces", "Uluwatu Temple", "Canggu Beaches"],
        "description": "An Indonesian paradise known for its forested volcanic mountains, iconic rice paddies, beaches, and coral reefs."
    },
    {
        "id": "reykjavik-iceland",
        "name": "Reykjavik",
        "country": "Iceland",
        "category": "Nature & Adventure",
        "budget_tier": "Luxury",
        "rating": 4.9,
        "avg_cost_per_day_usd": 250,
        "highlights": ["Northern Lights", "Blue Lagoon", "Golden Circle Route", "Black Sand Beaches"],
        "description": "Gateway to Iceland's dramatic volcanic landscape, geysers, hot springs, waterfalls, and mesmerizing aurora borealis."
    }
]

def seed_firestore():
    db = firestore.Client(project=PROJECT_ID, database="(default)")
    print(f"Seeding Firestore collection '{COLLECTION_NAME}' in project '{PROJECT_ID}'...")
    
    collection_ref = db.collection(COLLECTION_NAME)
    for dest in DESTINATIONS:
        doc_id = dest["id"]
        collection_ref.document(doc_id).set(dest)
        print(f"  ✓ Added destination: {dest['name']}, {dest['country']} (ID: {doc_id})")
        
    print("Firestore seeding complete! ✅")

if __name__ == "__main__":
    seed_firestore()
