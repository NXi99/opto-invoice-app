from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
import json
import pdfkit
from pathlib import Path
from datetime import datetime
from io import BytesIO
import smtplib
import ssl
from email.message import EmailMessage
import zipfile
import tempfile
from utils import update_description_cache, load_recent_descriptions, get_invoice_counter

app = Flask(__name__)
app.secret_key = 'opto-secret-key'

DATA_DIR = Path(".")
CUSTOMERS_FILE = DATA_DIR / "customers.json"
LOG_FILE = DATA_DIR / "invoice_log.json"
DESC_CACHE_FILE = DATA_DIR / "description_cache.json"

PDF_OUTPUT_DIR = DATA_DIR / "invoices"
PDF_OUTPUT_DIR.mkdir(exist_ok=True)

# === Load/Save Helpers ===
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
    descriptions = load_recent_descriptions(DESC_CACHE_FILE)
    return render_template("form.html", customers=customers, descriptions=descriptions)

@app.route("/get-invoice-number", methods=["POST"])
def get_invoice_number():
    customer_id = request.json.get("customer_id")
    number = get_invoice_counter(customer_id, LOG_FILE)
    return jsonify({"number": number})

@app.route("/generate", methods=["POST"])
def generate():
    customers = load_customers()
    customer_id = request.form.get("customer_id")
    description = request.form.get("description")
    email_address = request.form.get("email")
    amount_incl = request.form.get("amount_incl")

    if not (customer_id and description and amount_incl):
        flash("Vul alle velden in.", "error")
        return redirect(url_for("index"))

    try:
        incl = float(amount_incl)
    except ValueError:
        flash("Voer een geldig bedrag in.", "error")
        return redirect(url_for("index"))

    excl = round(incl / 1.21, 2)
    vat = round(incl - excl, 2)

    info = customers[customer_id]
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
        "amount_incl": f"€ {incl:,.2f}"
    }

    html = render_template("Opto.html", **context)
    footer_html = render_template("footer.html", **context)

    footer_path = Path("footer_temp.html")
    with open(footer_path, "w", encoding="utf-8") as f:
        f.write(footer_html)

    config = pdfkit.configuration(wkhtmltopdf='/usr/bin/wkhtmltopdf')
    options = {
        'enable-local-file-access': '',
        'encoding': 'UTF-8',
        'margin-top': '20mm',
        'margin-bottom': '30mm',
        'footer-html': str(footer_path.resolve())
    }

    pdf_data = pdfkit.from_string(html, False, configuration=config, options=options)
    pdf_filename = f"{invoice_number}_{info['name'].split()[0]}.pdf"

    (PDF_OUTPUT_DIR / pdf_filename).write_bytes(pdf_data)
    footer_path.unlink(missing_ok=True)

    # Save recent description
    update_description_cache(description, DESC_CACHE_FILE)

    # Send email if requested
    if email_address:
        try:
            msg = EmailMessage()
            msg['Subject'] = f"Factuur {invoice_number}"
            msg['From'] = "no-reply@optoinvoice.com"
            msg['To'] = email_address
            msg.set_content("In de bijlage vindt u uw factuur als PDF.")
            msg.add_attachment(pdf_data, maintype='application', subtype='pdf', filename=pdf_filename)

            context = ssl.create_default_context()
            with smtplib.SMTP_SSL('smtp.example.com', 465, context=context) as smtp:
                smtp.login('your_username', 'your_password')
                smtp.send_message(msg)

            flash("Factuur verzonden naar e-mail.", "success")
        except Exception:
            flash("E-mail verzenden mislukt.", "error")

    flash("Factuur succesvol gegenereerd.", "success")
    return send_file(BytesIO(pdf_data), mimetype='application/pdf', as_attachment=True, download_name=pdf_filename)

@app.route("/preview", methods=["POST"])
def preview():
    customers = load_customers()
    customer_id = request.form.get("customer_id")
    description = request.form.get("description")
    amount_incl = request.form.get("amount_incl")

    if not (customer_id and description and amount_incl):
        return "Ontbrekende gegevens."

    try:
        incl = float(amount_incl)
    except ValueError:
        return "Ongeldig bedrag."

    excl = round(incl / 1.21, 2)
    vat = round(incl - excl, 2)

    info = customers[customer_id]
    invoice_number = "VOORBEELD"
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
        "amount_incl": f"€ {incl:,.2f}"
    }
    return render_template("Opto.html", **context)

@app.route("/download-logs")
def download_logs():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        with zipfile.ZipFile(tmp, 'w') as zipf:
            for file_path in [CUSTOMERS_FILE, LOG_FILE]:
                if file_path.exists():
                    zipf.write(file_path, arcname=file_path.name)
        tmp.seek(0)
        return send_file(tmp.name, as_attachment=True, download_name="opto_logs.zip")

if __name__ == "__main__":
    app.run(debug=True)
