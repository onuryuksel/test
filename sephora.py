import streamlit as st
import pandas as pd
import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlparse, urljoin
import time

st.set_page_config(page_title="Brand Counter", layout="centered")

st.title("Brand & Count Extractor (Sephora PLP URL)3")

st.write(
    "Paste a **Sephora product‑listing URL** and hit *Fetch & Parse*. The app tries:\n"
    "1. Directly download the HTML (browser‑like headers, retries).\n"
    "2. If that stalls (>> 20 s) it falls back to Sephora's hidden *Search‑UpdateGrid* API, which is lighter and rarely blocked.\n"
    "3. Finally, if both fail, you can still upload a saved HTML file.\n"
)

# ----------------------------------------------------------------------------------------
# Helpers                                                                                 
# ----------------------------------------------------------------------------------------

def requests_session() -> requests.Session:
    sess = requests.Session()
    retries = Retry(total=3, backoff_factor=1.3, status_forcelist=[429, 500, 502, 503, 504])
    sess.mount("https://", HTTPAdapter(max_retries=retries))
    sess.mount("http://", HTTPAdapter(max_retries=retries))
    return sess


def fetch_html(url: str, timeout: int = 15) -> str | None:
    """Try to grab full HTML – returns None if blocked/timeouts."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "close",
    }
    try:
        resp = requests_session().get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException:
        return None


def grid_endpoint_from_plp(plp_url: str) -> str | None:
    """Build the lightweight Search-UpdateGrid endpoint from PLP path (works for most locales)."""
    parsed = urlparse(plp_url)
    if not parsed.path:
        return None
    # Find last path segment that looks like a category ID (e.g. C301)
    parts = [p for p in parsed.path.split("/") if p]
    cat = next((p for p in reversed(parts) if p.startswith("C") and p[1:].isdigit()), None)
    if not cat:
        return None
    # Determine site slug heuristically
    domain = parsed.netloc
    if "sephora.me" in domain:
        site_slug = "Sites-SephoraGcc-Site"
    elif "sephora.ae" in domain:
        site_slug = "Sites-Sephora_AE-Site"
    else:
        # fallback guess (might still work)
        site_slug = "Sites-Sephora-Site"
    endpoint_path = f"/on/demandware.store/{site_slug}/en/Search-UpdateGrid?cgid={cat}&start=0&sz=300&format=page-element"
    return urljoin(f"{parsed.scheme}://{parsed.netloc}", endpoint_path)


def fetch_grid_json(url: str) -> str | None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_4 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,*/*",  # endpoint returns HTML snippet with JSON inside
        "Connection": "close",
    }
    try:
        resp = requests_session().get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException:
        return None


# ---------------------------- Brand extraction ------------------------------------------

def parse_brands(html_text: str) -> pd.DataFrame:
    pattern = r'\\"hitCount\\":\s*(\d+),\\"label\\":\\"([^"\\]+)\\"'
    matches = re.findall(pattern, html_text)

    def valid(label: str):
        return any(c.isalpha() for c in label) and label.isupper()

    totals: dict[str, int] = {}
    for cnt, lbl in matches:
        if valid(lbl):
            totals[lbl] = max(int(cnt), totals.get(lbl, 0))
    return pd.DataFrame(sorted(totals.items()), columns=["Brand", "Count"])

# ---------------------------- UI ---------------------------------------------------------

mode = st.radio("Choose input method", ["URL", "Upload HTML"], horizontal=True)

if mode == "URL":
    plp_url = st.text_input("Sephora PLP URL", placeholder="https://www.sephora.xx/...", label_visibility="visible")
    if st.button("Fetch & Parse", disabled=not plp_url.strip()):
        if not plp_url.startswith("http"):
            st.error("Enter a proper http/https URL.")
            st.stop()
        spinner = st.empty()
        spinner.info("Fetching full HTML …  (will retry via API fallback if needed)")
        html_full = fetch_html(plp_url)
        if html_full:
            df = parse_brands(html_full)
        else:
            spinner.warning("Full HTML fetch blocked – trying lightweight API …")
            grid_url = grid_endpoint_from_plp(plp_url)
            if not grid_url:
                st.error("Cannot infer API endpoint – try uploading the saved HTML instead.")
                st.stop()
            html_grid = fetch_grid_json(grid_url)
            if not html_grid:
                st.error("API fetch also blocked – Sephora edge is strict. Save page as HTML and choose *Upload HTML* mode.")
                st.stop()
            df = parse_brands(html_grid)
        spinner.empty()
        if df.empty:
            st.warning("No brands detected – maybe this PLP uses a new structure. Upload HTML instead.")
            st.stop()
        st.success(f"Found {len(df)} brands ✨")
        st.dataframe(df, use_container_width=True)
        st.download_button(
            "Download CSV",
            df.to_csv(index=False, encoding="utf-8"),
            "brand_counts.csv",
            "text/csv",
        )
else:  # Upload HTML
    up_file = st.file_uploader("Upload saved HTML", type=["html", "htm"])
    if up_file is not None:
        html_text = up_file.read().decode("utf-8", errors="ignore")
        df = parse_brands(html_text)
        if df.empty:
            st.warning("No brand JSON found – maybe wrong file? Try saving the PLP with ‘Webpage, Complete’ option.")
        else:
            st.success(f"Found {len(df)} brands.")
            st.dataframe(df, use_container_width=True)
            st.download_button(
                "Download CSV",
                df.to_csv(index=False, encoding="utf-8"),
                "brand_counts.csv",
                "text/csv",
            )

st.caption("Handles tough Sephora locales with HTML ➜ API fallback. If all fails, upload saved HTML.")
