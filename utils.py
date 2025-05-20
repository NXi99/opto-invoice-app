import json
from pathlib import Path


def update_description_cache(description, cache_path):
    descriptions = load_recent_descriptions(cache_path)
    if description not in descriptions:
        descriptions.insert(0, description)
        if len(descriptions) > 10:
            descriptions = descriptions[:10]
        with open(cache_path, 'w') as f:
            json.dump(descriptions, f, indent=2)


def load_recent_descriptions(cache_path):
    if Path(cache_path).exists():
        with open(cache_path, 'r') as f:
            return json.load(f)
    return []


def get_invoice_counter(customer_id, log_path):
    from datetime import datetime
    year = str(datetime.now().year)
    key = f"{year}-{str(customer_id).zfill(2)}"
    if Path(log_path).exists():
        with open(log_path, 'r') as f:
            log = json.load(f)
            return log.get(key, 0)
    return 0
