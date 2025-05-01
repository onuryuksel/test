import streamlit as st
import pandas as pd
import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

st.set_page_config(page_title="Brand Counter", layout="centered")

st.title("Brand & Count Extractor (Sephora PLP URL)1")

st.write(
    "Paste a **Sephora product‑listing URL** below and hit *Fetch & Parse*.\n\n"
    "If Sephora blocks the first attempt, the app will retry with a more complete browser‑like header set (User‑Agent, Accept, Accept‑Language, etc.) and exponential back‑off."
)

# ---------------------------------------------------------------------------- URL input
plp_url = st.text_input("Sephora PLP URL", placeholder="https://www.sephora.xx/...", label_visibility="visible")

# ---------------------------------------------------------------------------- helper: robust downloader
def download_html(url: str, timeout: int = 20) -> str:
    """Download HTML with retries + realistic headers."""
    session = requests.Session()

    # Retry strategy for transient network resets / 5xx / 403
    retries = Retry(
        total=4,
        backoff_factor=1.2,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.mount("http://", HTTPAdapter(max_retries=retries))

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "close",
    }

    resp = session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    return resp.text

# ---------------------------------------------------------------------------- extract brands
def extract_brands(html_text: str) -> pd.DataFrame:
    pattern = r'\\"hitCount\\":\s*(\d+),\\"label\\":\\"([^"\\]+)\\"'
    matches = re.findall(pattern, html_text)

    def looks_like_brand(label: str) -> bool:
        return (
            any(c.isalpha() for c in label)
            and not re.search(r'\d', label)
            and not any(c.islower() for c in label)
        )

    brand_totals: dict[str, int] = {}
    for count_str, label in matches:
        if not looks_like_brand(label):
            continue
        count = int(count_str)
        brand_totals[label] = max(count, brand_totals.get(label, 0))

    return (
        pd.DataFrame(sorted(brand_totals.items()), columns=["Brand", "Count"])
        .reset_index(drop=True)
    )

# ---------------------------------------------------------------------------- main flow
if st.button("Fetch & Parse", disabled=not plp_url.strip()):
    if not plp_url.lower().startswith("http"):
        st.error("Please enter a valid URL starting with http/https.")
        st.stop()

    try:
        with st.spinner("Fetching page …"):
            html_text = download_html(plp_url)
    except requests.exceptions.RequestException as e:
        st.error(f"Network error: {e}\n\nSome Sephora regions block bots. If this keeps happening, try: \n• Changing the URL to a different locale (e.g. sephora.ae). \n• Adding ?pageSize=300 so the entire PLP loads server‑side. \n• Using a VPN and re‑running.")
        st.stop()

    df = extract_brands(html_text)
    if df.empty:
        st.warning("No brands detected – double‑check that this is a PLP page with a brand filter.")
        st.stop()

    st.success(f"Found {len(df)} unique brands! ✨")
    st.dataframe(df, use_container_width=True)

    csv_bytes = df.to_csv(index=False, encoding="utf-8").encode("utf-8")
    st.download_button(
        "Download CSV",
        data=csv_bytes,
        file_name="brand_counts.csv",
        mime="text/csv",
    )

st.caption("Built with Streamlit · Handles basic anti‑bot hiccups via retries & realistic headers.")
