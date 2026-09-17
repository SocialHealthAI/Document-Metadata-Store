#!/bin/bash

# Download Healthy People Literature Summary
# and Citations and format in clean reading mode.
# Run using bash ./setup_and_run_scrape.sh

if command -v python3 &>/dev/null; then
    PY_BIN="python3"
elif command -v python &>/dev/null; then
    PY_BIN="python"
else
    echo "ERROR: Neither 'python3' nor 'python' was found in your PATH."
    exit 1
fi

echo "Using Python executable: $PY_BIN"

# Create a unique temporary directory for the environment
VENV_DIR=$(mktemp -d 2>/dev/null || mktemp -d -t 'pdf_env_XXXXXX')

echo "=== 1. Creating temporary Python virtual environment in $VENV_DIR ==="
"$PY_BIN" -m venv "$VENV_DIR" || { echo "Failed to create venv"; exit 1; }

# Ensure cleanup on script exit or interrupt
cleanup() {
    echo "=== 4. Cleaning up temporary environment ==="
    rm -rf "$VENV_DIR"
    echo "Temporary environment removed."
}
trap cleanup EXIT

# Determine virtual environment activation script
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
elif [ -f "$VENV_DIR/Scripts/activate" ]; then
    source "$VENV_DIR/Scripts/activate"
else
    echo "ERROR: Could not find activation script in $VENV_DIR"
    exit 1
fi

echo "=== 2. Installing dependencies ==="
pip install --upgrade pip
pip install beautifulsoup4 weasyprint requests

echo "=== 3. Creating and running scrape.py ==="
cat << 'EOF' > scrape.py
import requests
import re
from bs4 import BeautifulSoup
from weasyprint import HTML

links = [
    ("Employment", "https://odphp.health.gov/healthypeople/priority-areas/social-determinants-health/literature-summaries/employment"),
    ("Food Insecurity", "https://odphp.health.gov/healthypeople/priority-areas/social-determinants-health/literature-summaries/food-insecurity"),
    ("Housing Instability", "https://odphp.health.gov/healthypeople/priority-areas/social-determinants-health/literature-summaries/housing-instability"),
    ("Poverty", "https://odphp.health.gov/healthypeople/priority-areas/social-determinants-health/literature-summaries/poverty"),
    ("Early Childhood Development and Education", "https://odphp.health.gov/healthypeople/priority-areas/social-determinants-health/literature-summaries/early-childhood-development-and-education"),
    ("Enrollment in Higher Education", "https://odphp.health.gov/healthypeople/priority-areas/social-determinants-health/literature-summaries/enrollment-higher-education"),
    ("High School Graduation", "https://odphp.health.gov/healthypeople/priority-areas/social-determinants-health/literature-summaries/high-school-graduation"),
    ("Language and Literacy", "https://odphp.health.gov/healthypeople/priority-areas/social-determinants-health/literature-summaries/language-and-literacy"),
    ("Access to Health Services", "https://odphp.health.gov/healthypeople/priority-areas/social-determinants-health/literature-summaries/access-health-services"),
    ("Access to Primary Care", "https://odphp.health.gov/healthypeople/priority-areas/social-determinants-health/literature-summaries/access-primary-care"),
    ("Health Literacy", "https://odphp.health.gov/healthypeople/priority-areas/social-determinants-health/literature-summaries/health-literacy"),
    ("Access to Foods That Support Healthy Dietary Patterns", "https://odphp.health.gov/healthypeople/priority-areas/social-determinants-health/literature-summaries/access-foods-support-healthy-dietary-patterns"),
    ("Crime and Violence", "https://odphp.health.gov/healthypeople/priority-areas/social-determinants-health/literature-summaries/crime-and-violence"),
    ("Environmental Conditions", "https://odphp.health.gov/healthypeople/priority-areas/social-determinants-health/literature-summaries/environmental-conditions"),
    ("Quality of Housing", "https://odphp.health.gov/healthypeople/priority-areas/social-determinants-health/literature-summaries/quality-housing"),
    ("Civic Participation", "https://odphp.health.gov/healthypeople/priority-areas/social-determinants-health/literature-summaries/civic-participation"),
    ("Incarceration", "https://odphp.health.gov/healthypeople/priority-areas/social-determinants-health/literature-summaries/incarceration"),
    ("Social Cohesion", "https://odphp.health.gov/healthypeople/priority-areas/social-determinants-health/literature-summaries/social-cohesion")
]

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

css_style = """
@page {
    size: letter;
    margin: 20mm 18mm;
    @bottom-center {
        content: counter(page);
        font-family: Helvetica, Arial, sans-serif;
        font-size: 9pt;
        color: #718096;
    }
}
body {
    font-family: 'Georgia', serif;
    color: #2d3748;
    line-height: 1.6;
    margin: 0;
}
.header-banner {
    border-bottom: 2px solid #2b6cb0;
    padding-bottom: 12px;
    margin-bottom: 24px;
}
.source-tag {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 9pt;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #2b6cb0;
    margin-bottom: 6px;
}
h1 {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 20pt;
    color: #1a202c;
    margin: 0 0 6px 0;
}
.meta-info {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 9pt;
    color: #718096;
}
.content {
    font-size: 10.5pt;
}
h2 {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 14pt;
    color: #2c5282;
    margin-top: 22px;
    margin-bottom: 10px;
    border-left: 4px solid #3182ce;
    padding-left: 10px;
    page-break-after: avoid;
}
p {
    margin-bottom: 12px;
    text-align: justify;
}
ul, ol {
    margin-bottom: 12px;
    padding-left: 20px;
}
li {
    margin-bottom: 6px;
}
a {
    color: #2b6cb0;
    text-decoration: none;
}
"""

for title, url in links:
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.content, 'html.parser')
        
        main_content = soup.find('article') or soup.find('main') or soup.body
        
        for elem in main_content.find_all(['nav', 'header', 'footer', 'script', 'style', 'form', 'iframe']):
            elem.decompose()
            
        filename = f"Healthy People 2030 (in 2026), {title}.pdf"
        
        html_doc = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>{css_style}</style>
        </head>
        <body>
            <div class="header-banner">
                <div class="source-tag">Healthy People 2030 • Social Determinants of Health</div>
                <h1>Healthy People 2030 (in 2026), {title}</h1>
                <div class="meta-info">Literature Summary & References | Source: odphp.health.gov</div>
            </div>
            <div class="content">
                {main_content.prettify()}
            </div>
        </body>
        </html>
        """
        
        HTML(string=html_doc, base_url=url).write_pdf(filename)
        print(f"Generated: {filename}")
    except Exception as e:
        print(f"Error on {title}: {e}")

print("Done! All PDFs generated successfully.")
EOF

python scrape.py