from flask import Flask, render_template, request, redirect, url_for, flash, send_file
import json
import pdfkit
from pathlib import Path
from datetime import datetime
from io import BytesIO

# Local utilities
from utils import (
    load_customers, save_customers,
    load_companies, save_companies, ensure_default_company,
    load_invoice_log, save_invoice_log, get_invoice_counter_scoped,
    update_description_cache
)

app = Flask(__name__)
app.secret_key = 'opto-secret-key'

DATA_DIR = Path(".")
CUSTOMERS_FILE = DATA_DIR / "customers.json"
COMPANIES_FILE = DATA_DIR / "companies.json"          # New: companies store
LOG_FILE = DATA_DIR / "invoice_log.json"              # Reused, but keys are now scoped by company+customer+year
DESC_CACHE_FILE = DATA_DIR / "recent_descriptions.json"

# === Home ===
@app.route("/")
def index():
    """
    Render main form with both customers and companies.
    """
    customers = load_customers(CUSTOMERS_FILE)
    companies = load_companies(COMPANIES_FILE)
    # Seed a default company when companies.json doesn't exist yet
    if not companies:
        companies = ensure_default_company(COMPANIES_FILE)
    return render_template("form.html", customers=customers, companies=companies)

# === Generate PDF ===
@app.route("/generate", methods=["POST"])
def generate():
    """
    Generate invoice PDF with company-specific branding and per-company counters.
    Keeps existing invoice number format but counters are scoped per (company_id, customer_id, year).
    """
    customers = load_customers(CUSTOMERS_FILE)
    companies = load_companies(COMPANIES_FILE)
    if not companies:
        companies = ensure_default_company(COMPANIES_FILE)

    company_id = request.form.get("company_id")
    customer_id = request.form.get("customer_id")
    description = request.form.get("description")
    amount_incl = request.form.get("amount_incl")

    # Basic form validation
    if not (company_id and customer_id and description and amount_incl):
        flash("Vul alle velden in.")
        return redirect(url_for("index"))

    if company_id not in companies:
        flash("Ongeldig bedrijf geselecteerd.")
        return redirect(url_for("index"))

    if customer_id not in customers:
        flash("Ongeldige klant geselecteerd.")
        return redirect(url_for("index"))

    try:
        incl = float(amount_incl)
    except ValueError:
        flash("Voer een geldig bedrag in.")
        return redirect(url_for("index"))

    # Compute VAT/excluding amounts (21% VAT)
    excl = round(incl / 1.21, 2)
    vat = round(incl - excl, 2)

    # Retrieve customer & company info
    c_info = customers[customer_id]
    co_info = companies[company_id]

    # Per-company+customer+year counter
    year = str(datetime.now().year)
    sequence = get_invoice_counter_scoped(company_id, customer_id, LOG_FILE)
    sequence += 1  # next number
    # Persist updated counter
    log = load_invoice_log(LOG_FILE)
    key = f"{year}-COMP{str(company_id).zfill(2)}-CUST{str(customer_id).zfill(2)}"
    log[key] = sequence
    save_invoice_log(LOG_FILE, log)

    # Keep your existing number pattern (year-customerID + 2-digit sequence)
    # This avoids breaking any downstream expectations you might have.
    invoice_number = f"{year}-{str(customer_id).zfill(2)}{sequence:02d}"
    invoice_date = datetime.now().strftime("%d-%m-%Y")

    # Cache the description for quick reuse if you later add a picker (optional UX)
    update_description_cache(description, DESC_CACHE_FILE)

    # Context for templates
    context = {
        # Invoice core
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        # Customer
        "customer_name": c_info["name"],
        "customer_address_line1": c_info.get("address_line1", ""),
        "customer_address_line2": c_info.get("address_line2", ""),
        # Line item
        "description": description,
        "amount_excl": f"€ {excl:,.2f}",
        "vat_amount": f"€ {vat:,.2f}",
        "amount_incl": f"€ {incl:,.2f}",
        # Company branding (used in header + footer)
        "company_name": co_info.get("name", ""),
        "company_address_line1": co_info.get("address_line1", ""),
        "company_address_line2": co_info.get("address_line2", ""),
        "company_kvk": co_info.get("kvk", ""),
        "company_btw": co_info.get("btw", ""),
        "company_iban": co_info.get("iban", ""),
    }

    html = render_template("opto.html", **context)
    footer_html = render_template("footer.html", **context)

    # Footer temp file for wkhtmltopdf footer-html option
    footer_path = Path("footer_temp.html")
    with open(footer_path, "w", encoding="utf-8") as f:
        f.write(footer_html)

    # Render to PDF
    config = pdfkit.configuration(wkhtmltopdf='/usr/bin/wkhtmltopdf')
    options = {
        'enable-local-file-access': '',
        'encoding': 'UTF-8',
        'margin-top': '20mm',
        'margin-bottom': '30mm',
        'footer-html': str(footer_path.resolve())
    }

    pdf_data = pdfkit.from_string(html, False, configuration=config, options=options)
    pdf_filename = f"{invoice_number}_{c_info['name'].split()[0]}.pdf"

    # Cleanup
    footer_path.unlink(missing_ok=True)

    return send_file(
        BytesIO(pdf_data),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=pdf_filename
    )

# === Customers ===
@app.route("/add-customer", methods=["GET", "POST"])
def add_customer():
    """
    Add a new customer (unchanged logic; UI remains in Dutch).
    """
    customers = load_customers(CUSTOMERS_FILE)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        addr1 = request.form.get("address_line1", "").strip()
        addr2 = request.form.get("address_line2", "").strip()

        if not name:
            flash("Naam mag niet leeg zijn.")
            return redirect(url_for("add_customer"))

        next_id = str(max([int(i) for i in customers.keys()] + [0]) + 1)
        customers[next_id] = {
            "name": name,
            "address_line1": addr1,
            "address_line2": addr2
        }
        save_customers(CUSTOMERS_FILE, customers)
        flash("Klant toegevoegd.")
        return redirect(url_for("add_customer"))

    return render_template("add_customer.html")

@app.route("/edit-customer", methods=["GET", "POST"])
def edit_customer():
    """
    Edit or delete a customer (unchanged logic; UI remains in Dutch).
    """
    customers = load_customers(CUSTOMERS_FILE)
    if request.method == "POST":
        cid = request.form.get("selected_id")
        action = request.form.get("action")

        if action == "delete":
            if cid in customers:
                del customers[cid]
                save_customers(CUSTOMERS_FILE, customers)
                flash("Klant verwijderd.")
        elif action == "update":
            name = request.form.get("name", "").strip()
            addr1 = request.form.get("address_line1", "").strip()
            addr2 = request.form.get("address_line2", "").strip()

            if cid in customers:
                if name:
                    customers[cid]["name"] = name
                customers[cid]["address_line1"] = addr1
                customers[cid]["address_line2"] = addr2
                save_customers(CUSTOMERS_FILE, customers)
                flash("Klantgegevens bijgewerkt.")

        return redirect(url_for("edit_customer"))

    return render_template("edit_customer.html", customers=customers)

# === Companies (new) ===
@app.route("/bedrijven", methods=["GET"])
def companies_list():
    """
    List companies (admin UX).
    """
    companies = load_companies(COMPANIES_FILE)
    if not companies:
        companies = ensure_default_company(COMPANIES_FILE)
    return render_template("companies_list.html", companies=companies)

@app.route("/bedrijf-toevoegen", methods=["GET", "POST"])
def add_company():
    """
    Create a new company profile.
    """
    companies = load_companies(COMPANIES_FILE)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        addr1 = request.form.get("address_line1", "").strip()
        addr2 = request.form.get("address_line2", "").strip()
        kvk = request.form.get("kvk", "").strip()
        btw = request.form.get("btw", "").strip()
        iban = request.form.get("iban", "").strip()

        if not name:
            flash("Bedrijfsnaam mag niet leeg zijn.")
            return redirect(url_for("add_company"))

        next_id = str(max([int(i) for i in companies.keys()] + [0]) + 1)
        companies[next_id] = {
            "name": name,
            "address_line1": addr1,
            "address_line2": addr2,
            "kvk": kvk,
            "btw": btw,
            "iban": iban
        }
        save_companies(COMPANIES_FILE, companies)
        flash("Bedrijf toegevoegd.")
        return redirect(url_for("companies_list"))

    return render_template("add_company.html")

@app.route("/bedrijf-bewerken", methods=["GET", "POST"])
def edit_company():
    """
    Update or delete a company profile.
    """
    companies = load_companies(COMPANIES_FILE)
    if request.method == "POST":
        co_id = request.form.get("selected_id")
        action = request.form.get("action")

        if action == "delete":
            if co_id in companies:
                del companies[co_id]
                save_companies(COMPANIES_FILE, companies)
                flash("Bedrijf verwijderd.")
        elif action == "update":
            name = request.form.get("name", "").strip()
            addr1 = request.form.get("address_line1", "").strip()
            addr2 = request.form.get("address_line2", "").strip()
            kvk = request.form.get("kvk", "").strip()
            btw = request.form.get("btw", "").strip()
            iban = request.form.get("iban", "").strip()

            if co_id in companies:
                if name:
                    companies[co_id]["name"] = name
                companies[co_id]["address_line1"] = addr1
                companies[co_id]["address_line2"] = addr2
                companies[co_id]["kvk"] = kvk
                companies[co_id]["btw"] = btw
                companies[co_id]["iban"] = iban
                save_companies(COMPANIES_FILE, companies)
                flash("Bedrijfsgegevens bijgewerkt.")

        return redirect(url_for("edit_company"))

    return render_template("edit_company.html", companies=companies)

# === Reset counter (now scoped by company + customer + year) ===
@app.route("/reset-counter", methods=["GET", "POST"])
def reset_counter():
    """
    Reset invoice counter for a specific (company, customer, current year).
    """
    customers = load_customers(CUSTOMERS_FILE)
    companies = load_companies(COMPANIES_FILE)
    if not companies:
        companies = ensure_default_company(COMPANIES_FILE)

    log = load_invoice_log(LOG_FILE)
    year = str(datetime.now().year)

    if request.method == "POST":
        co_id = request.form.get("company_id")
        cid = request.form.get("customer_id")
        try:
            new_value = int(request.form.get("new_value"))
            key = f"{year}-COMP{str(co_id).zfill(2)}-CUST{str(cid).zfill(2)}"
            log[key] = new_value
            save_invoice_log(LOG_FILE, log)
            flash("Factuurteller gereset.")
            return redirect(url_for("reset_counter"))
        except Exception:
            flash("Ongeldig nummer ingevoerd.")
            return redirect(url_for("reset_counter"))

    # Compute a simple view model with current counters
    # (useful to show in the UI)
    counters = []
    for co_id in companies.keys():
        for cid in customers.keys():
            k = f"{year}-COMP{str(co_id).zfill(2)}-CUST{str(cid).zfill(2)}"
            counters.append({
                "company_id": co_id,
                "customer_id": cid,
                "key": k,
                "value": log.get(k, 0)
            })

    return render_template("reset_counter.html",
                           customers=customers,
                           companies=companies,
                           invoice_log=log,
                           counters=counters)

if __name__ == "__main__":
    app.run(debug=True)
