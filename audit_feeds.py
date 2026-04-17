import feedparser
import json
from datetime import datetime, timezone

CUTOFF_DATE = datetime(2025, 10, 17, tzinfo=timezone.utc)

def main():
    active_recent = []
    stale = []
    errors = []

    try:
        with open('config/feeds.txt', 'r') as f:
            lines = f.readlines()
            urls = [line.strip() for line in lines if line.strip() and not line.strip().startswith('#')]
    except FileNotFoundError:
        print(json.dumps({"errors": [{"url": "config/feeds.txt", "error": "File not found"}]}))
        return

    # Process only first 5 to avoid timeout for demonstration if many feeds exist
    for url in urls:
        try:
            d = feedparser.parse(url)
            if d.get('bozo') and not d.entries:
                errors.append({"url": url, "error": str(d.get('bozo_exception', 'Bozo error'))})
                continue

            latest_date = None
            for entry in d.entries:
                dt = None
                if 'published_parsed' in entry and entry.published_parsed:
                    dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                elif 'updated_parsed' in entry and entry.updated_parsed:
                    dt = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
                
                if dt:
                    if latest_date is None or dt > latest_date:
                        latest_date = dt
            
            if latest_date:
                if latest_date >= CUTOFF_DATE:
                    active_recent.append(url)
                else:
                    stale.append({"url": url, "latest_date": latest_date.isoformat()})
            else:
                errors.append({"url": url, "error": "No dates found in entries"})
        except Exception as e:
            errors.append({"url": url, "error": str(e)})

    print(json.dumps({
        "active_recent": active_recent,
        "stale": stale,
        "errors": errors
    }, indent=4))

if __name__ == "__main__":
    main()
