
import sys, os, logging
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from src.store import Store
from src.models import Individual
from src.fetcher import fetch_recent_videos, fetch_transcript
from src.extractor import extract_predictions

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "predictions.json")
SINCE_DATE = date(2024, 1, 1)
ALL_CATEGORIES = ["finance", "energy", "ukraine", "china", "ai", "geopolitics"]

def seed():
    store = Store(DATA_PATH)
    
    individuals = [
        Individual(
            name="Peter Zeihan",
            handle="zeihan",
            sources=["https://www.youtube.com/@ZeihanonGeopolitics/videos"],
            categories=["geopolitics", "energy", "china", "ukraine", "finance"]
        ),
        Individual(
            name="Doomberg",
            handle="doomberg",
            sources=["https://newsletter.doomberg.com", "https://www.youtube.com/results?search_query=doomberg"],
            categories=["energy", "finance", "geopolitics"]
        ),
        Individual(
            name="Peter Diamandis",
            handle="diamandis",
            sources=["https://www.youtube.com/@PeterHDiamandis/videos"],
            categories=["ai"]
        ),
    ]
    
    for ind in individuals:
        store.add_individual(ind)
        logger.info("Added: %s (%s) - %s", ind.name, ind.handle, ind.categories)

    # Fetch videos and extract predictions
    for ind in individuals:
        logger.info("Fetching videos for %s...", ind.name)
        total_preds = 0

        for source_url in ind.sources:
            if "youtube.com" not in source_url:
                logger.info("  Skipping non-YouTube source: %s", source_url)
                continue

            try:
                videos = fetch_recent_videos(source_url, SINCE_DATE, limit=10)
                logger.info("  Found %d videos from %s", len(videos), source_url)

                for video in videos:
                    logger.info("    Processing: %s (%s)", video.title, video.upload_date)
                    transcript = fetch_transcript(video.id)
                    if not transcript:
                        logger.info("      No transcript available, skipping")
                        continue
                    preds = extract_predictions(
                        transcript=transcript,
                        video_url=video.url,
                        individual_name=ind.name,
                        categories=ALL_CATEGORIES,
                        upload_date=video.upload_date,
                    )
                    for pred in preds:
                        store.add_prediction(pred)
                        total_preds += 1
                        logger.info("      Extracted: [%s] %s", pred.category, pred.claim[:80])
            except Exception as e:
                logger.error("  Error fetching %s: %s", source_url, e)
                continue

        logger.info("Total predictions for %s: %d", ind.name, total_preds)
    
    total = len(store.get_all())
    logger.info("Seed complete! Total predictions in store: %d", total)

if __name__ == "__main__":
    seed()
