import streamlit as st
import pandas as pd
import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlparse, urljoin

st.set_page_config(page_title="Brand Counter", layout="centered")

st.title("Brand & Count Extractor — Sephora PLP")

st.write(
    "1. Paste any **Sephora product-listing URL** (e.g. fragrance, makeup…).\n"
    "2. *(Optional)* paste your **Cookie** header from DevTools if the site blocks bots.\n"
    "3. Hit **Fetch & Parse** — you’ll get one row per brand plus a CSV download.\n"
)

# -----------------------------------------------------------------------------------------
# Utilities                                                                                
# -----------------------------------------------------------------------------------------

def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=1.2, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


def fetch_html(url: str, cookies: str | None = None, timeout: int = 15) -> str | None:
    """Try to fetch the full HTML with realistic headers (optionally user-supplied cookies)."""
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
    if cookies:
        headers["Cookie"] = cookies.strip()
    try:
        resp = make_session().get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException:
        return None


def build_grid_url(plp_url: str) -> str | None:
    """Construct the Search-UpdateGrid endpoint used by Sephora’s facet API."""
    parsed = urlparse(plp_url)
    parts = [p for p in parsed.path.split("/") if p]
    cat = next((p for p in reversed(parts) if p.startswith("C") and p[1:].isdigit()), None)
    if not cat:
        return None
    if "sephora.me" in parsed.netloc:
        slug = "Sites-SephoraGcc-Site"
    elif "sephora.ae" in parsed.netloc:
        slug = "Sites-Sephora_AE-Site"
    else:
        slug = "Sites-Sephora-Site"
    path = f"/on/demandware.store/{slug}/en/Search-UpdateGrid?cgid={cat}&start=0&sz=300&format=page-element"
    return urljoin(f"{parsed.scheme}://{parsed.netloc}", path)


def fetch_grid_html(url: str, cookies: str | None = None) -> str | None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_4 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,*/*",
        "Connection": "close",
    }
    if cookies:
        headers["Cookie"] = cookies.strip()
    try:
        resp = make_session().get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException:
        return None


def extract_brands(html: str) -> pd.DataFrame:
    pattern = r'\\"hitCount\\":\s*(\d+),\\"label\\":\\"([^"\\]+)\\"'
    pairs = re.findall(pattern, html)
    def is_brand(lbl: str):
        return any(c.isalpha() for c in lbl) and lbl.isupper()
    agg: dict[str, int] = {}
    for cnt, lbl in pairs:
        if is_brand(lbl):
            agg[lbl] = max(int(cnt), agg.get(lbl, 0))
    return pd.DataFrame(sorted(agg.items()), columns=["Brand", "Count"])

# -----------------------------------------------------------------------------------------
# UI                                                                                       
# -----------------------------------------------------------------------------------------

plp_url = st.text_input("PLP URL", placeholder="https://www.sephora.me/…")
cookie_str = st.text_input("Optional Cookie header (paste from DevTools)")

col1, col2 = st.columns([1, 6])
with col1:
    go = st.button("Fetch & Parse", disabled=not plp_url.strip())

if go:
    if not plp_url.startswith("http"):
        st.error("Provide a valid http/https URL.")
        st.stop()

    st.info("Step 1 /2: Fetching full HTML …")
    html_full = fetch_html(plp_url, cookie_str or None)

    if html_full:
        df = extract_brands(html_full)
    else:
        st.warning("Full HTML blocked – trying lightweight API …")
        grid_url = build_grid_url(plp_url)
        if not grid_url:
            st.error("Couldn’t infer API endpoint — paste cookies or save page & upload instead.")
            st.stop()
        html_grid = fetch_grid_html(grid_url, cookie_str or None)
        if not html_grid:
            st.error("API call also blocked. Double-check cookies, or use ‘Save Page As’ then rerun.")
            st.stop()
        df = extract_brands(html_grid)

    if df.empty:
        st.warning("No brands found – page structure might have changed.")
    else:
        st.success(f"Success – {len(df)} brands detected.")
        st.dataframe(df, use_container_width=True)
        st.download_button("Download CSV", df.to_csv(index=False).encode(), "brand_counts.csv", "text/csv")

st.caption("Tip: In Chrome, open DevTools → Network → any PLP request → ‘Headers’ → copy the full ‘Cookie’ line.")
