import json
from pathlib import Path
from datetime import datetime

# -----------------------------
# File I/O helpers (customers)
# -----------------------------
def load_customers(path):
    """Load customers.json or return empty dict."""
    path = Path(path)
    if path.exists():
        with open(path, 'r') as f:
            return json.load(f)
    return {}

def save_customers(path, data):
    """Persist customers.json."""
    with open(path, 'w') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# -----------------------------
# File I/O helpers (companies)
# -----------------------------
def load_companies(path):
    """Load companies.json or return empty dict."""
    path = Path(path)
    if path.exists():
        with open(path, 'r') as f:
            return json.load(f)
    return {}

def save_companies(path, data):
    """Persist companies.json."""
    with open(path, 'w') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def ensure_default_company(path):
    """
    Seed a default company if companies.json is missing/empty.
    Returns the resulting companies dict.
    """
    path = Path(path)
    companies = load_companies(path)
    if companies:
        return companies

    # Create company "1" based on your current hard-coded branding
    companies = {
        "1": {
            "name": "Opto Optiek B.V.",
            "address_line1": "Schout Saelberngenplantsoen 10",
            "address_line2": "5911 EN Panningen",
            "kvk": "66780241",
            "btw": "NL856694691B01",
            "iban": "NL25 INGB 0733738028"
        }
    }
    save_companies(path, companies)
    return companies

# -----------------------------
# Invoice log (counters)
# -----------------------------
def load_invoice_log(path):
    """Load invoice_log.json, or return empty dict."""
    path = Path(path)
    if path.exists():
        with open(path, 'r') as f:
            return json.load(f)
    return {}

def save_invoice_log(path, log):
    """Persist invoice_log.json."""
    with open(path, 'w') as f:
        json.dump(log, f, indent=4, ensure_ascii=False)

def get_invoice_counter_scoped(company_id, customer_id, log_path):
    """
    Return current counter for (company_id, customer_id, year).
    If missing, return 0.
    Key format: "{year}-COMP{company_id:02d}-CUST{customer_id:02d}"
    """
    year = str(datetime.now().year)
    key = f"{year}-COMP{str(company_id).zfill(2)}-CUST{str(customer_id).zfill(2)}"
    log = load_invoice_log(log_path)
    return log.get(key, 0)

# -----------------------------
# Description cache (optional UX)
# -----------------------------
def update_description_cache(description, cache_path):
    """
    Maintain a most-recently-used list of up to 10 descriptions.
    Useful for a future autocomplete/select UI.
    """
    descriptions = load_recent_descriptions(cache_path)
    if description and description not in descriptions:
        descriptions.insert(0, description)
        if len(descriptions) > 10:
            descriptions = descriptions[:10]
        with open(cache_path, 'w') as f:
            json.dump(descriptions, f, indent=2, ensure_ascii=False)

def load_recent_descriptions(cache_path):
    """Load recent descriptions cache; return list."""
    if Path(cache_path).exists():
        with open(cache_path, 'r') as f:
            return json.load(f)
    return []
