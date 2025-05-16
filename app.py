from flask import Flask, render_template, request, redirect, url_for, flash, send_file
import json
import pdfkit
from pathlib import Path
from datetime import datetime
from io import BytesIO

app = Flask(__name__)
app.secret_key = 'opto-secret-key'

DATA_DIR = Path(".")
CUSTOMERS_FILE = DATA_DIR / "customers.json"
LOG_FILE = DATA_DIR / "invoice_log.json"

# === Helpers ===
def load_customers():
    if CUSTOMERS_FILE.exists():
        with open(CUSTOMERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_customers(data):
    with open(CUSTOMERS_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def load_invoice_log():
    if LOG_FILE.exists():
        with open(LOG_FILE, 'r') as f:
            return json.load(f)
    return {}

def update_invoice_log(customer_id):
    log = load_invoice_log()
    year = str(datetime.now().year)
    key = f"{year}-{str(customer_id).zfill(2)}"
    log[key] = log.get(key, 0) + 1
    with open(LOG_FILE, 'w') as f:
        json.dump(log, f, indent=4)
    return log[key]

@app.route("/")
def index():
    customers = load_customers()
    return render_template("form.html", customers=customers)

@app.route("/generate", methods=["POST"])
def generate():
    customers = load_customers()
    customer_id = request.form.get("customer_id")
    description = request.form.get("description")
    amount_excl = request.form.get("amount_excl")

    if not (customer_id and description and amount_excl):
        flash("Vul alle velden in.")
        return redirect(url_for("index"))

    try:
        excl = float(amount_excl)
    except ValueError:
        flash("Voer een geldig bedrag in.")
        return redirect(url_for("index"))

    info = customers[customer_id]
    vat = round(excl * 0.21, 2)
    total = round(excl + vat, 2)

    year = str(datetime.now().year)
    sequence = update_invoice_log(customer_id)
    invoice_number = f"{year}-{str(customer_id).zfill(2)}{sequence:02d}"
    invoice_date = datetime.now().strftime("%d-%m-%Y")

    context = {
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "customer_name": info["name"],
        "customer_address_line1": info["address_line1"],
        "customer_address_line2": info["address_line2"],
        "description": description,
        "amount_excl": f"€ {excl:,.2f}",
        "vat_amount": f"€ {vat:,.2f}",
        "amount_incl": f"€ {total:,.2f}"
    }

    html = render_template("Opto.html", **context)
    footer_html = render_template("footer.html", **context)

    footer_path = Path("footer_temp.html")

    config = pdfkit.configuration(wkhtmltopdf='/usr/bin/wkhtmltopdf')
    options = {
        'enable-local-file-access': '',
        'encoding': 'UTF-8',
        'margin-top': '20mm',
        'margin-bottom': '60mm',
        'footer-html': str(footer_path.resolve())
    }

    pdf_data = pdfkit.from_string(html, False, configuration=config, options=options)
    pdf_filename = f"{invoice_number}_{info['name'].split()[0]}.pdf"

    footer_path.unlink(missing_ok=True)

    print("Using footer path:", footer_path.resolve())
    print("File exists:", footer_path.exists())

    return send_file(
        BytesIO(pdf_data),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=pdf_filename
    )

@app.route("/add-customer", methods=["GET", "POST"])
def add_customer():
    customers = load_customers()
    if request.method == "POST":
        name = request.form.get("name").strip()
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
        save_customers(customers)
        flash("Klant toegevoegd.")
        return redirect(url_for("index"))

    return render_template("add_customer.html")

@app.route("/edit-customer", methods=["GET", "POST"])
def edit_customer():
    customers = load_customers()
    if request.method == "POST":
        cid = request.form.get("selected_id")
        action = request.form.get("action")

        if action == "delete":
            if cid in customers:
                del customers[cid]
                save_customers(customers)
                flash("Klant verwijderd.")
        elif action == "update":
            name = request.form.get("name").strip()
            addr1 = request.form.get("address_line1", "").strip()
            addr2 = request.form.get("address_line2", "").strip()

            if cid in customers:
                if name:
                    customers[cid]["name"] = name
                customers[cid]["address_line1"] = addr1
                customers[cid]["address_line2"] = addr2
                save_customers(customers)
                flash("Klantgegevens bijgewerkt.")

        return redirect(url_for("edit_customer"))

    return render_template("edit_customer.html", customers=customers)

@app.route("/reset-counter", methods=["GET", "POST"])
def reset_counter():
    customers = load_customers()
    log = load_invoice_log()

    if request.method == "POST":
        cid = request.form.get("customer_id")
        try:
            new_value = int(request.form.get("new_value"))
            year = str(datetime.now().year)
            key = f"{year}-{str(cid).zfill(2)}"
            log[key] = new_value
            with open(LOG_FILE, 'w') as f:
                json.dump(log, f, indent=4)
            flash("Factuurteller gereset.")
            return redirect(url_for("index"))
        except:
            flash("Ongeldig nummer ingevoerd.")
            return redirect(url_for("reset_counter"))

    return render_template("reset_counter.html", customers=customers)

if __name__ == "__main__":
    app.run(debug=True)
