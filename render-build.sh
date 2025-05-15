#!/usr/bin/env bash

# Install wkhtmltopdf
curl -L -o wkhtmltox.deb https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6-1/wkhtmltox_0.12.6-1.bionic_amd64.deb
apt install -y ./wkhtmltox.deb
