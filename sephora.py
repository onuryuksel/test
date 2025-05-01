import streamlit as st
import pandas as pd
import re
import requests

st.set_page_config(page_title="Brand Counter", layout="centered")

st.title("Brand & Count Extractor (Sephora PLP URL)")

st.write(
    "🎯 **Paste a Sephora product‑listing (PLP) URL** below and click *Fetch & Parse*.\n"
    "The app will download the HTML on your behalf, extract one row per brand with its product count, and let you download a CSV. "
)

# --- URL input ---------------------------------------------------------------------------
plp_url = st.text_input("Sephora PLP URL", placeholder="https://www.sephora.xx/...", label_visibility="visible")

# --- Fetch + Parse button ----------------------------------------------------------------
if st.button("Fetch & Parse", disabled=not plp_url.strip()):
    if not plp_url.lower().startswith("http"):
        st.error("Please enter a valid URL starting with http/https.")
    else:
        try:
            with st.spinner("Downloading page …"):
                resp = requests.get(
                    plp_url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; BrandCounterBot/1.0)"},
                    timeout=15,
                )
                resp.raise_for_status()
                html_text = resp.text
        except requests.exceptions.RequestException as e:
            st.error(f"Error fetching the URL: {e}")
            st.stop()

        # -------- Extract brand data from embedded JSON ------------------------------
        pattern = r'\\"hitCount\\":\s*(\d+),\\"label\\":\\"([^"\\]+)\\"'
        matches = re.findall(pattern, html_text)

        def looks_like_brand(label: str) -> bool:
            return (
                any(c.isalpha() for c in label)  # has letters
                and not re.search(r'\d', label)  # exclude numeric labels/SKUs
                and not any(c.islower() for c in label)  # brand labels appear upper‑case in this blob
            )

        brand_totals: dict[str, int] = {}
        for count_str, label in matches:
            if not looks_like_brand(label):
                continue
            count = int(count_str)
            # Dedup logic: keep max count if label repeats
            brand_totals[label] = max(count, brand_totals.get(label, 0))

        if not brand_totals:
            st.warning("No brands detected – make sure you're using a PLP URL that contains the brand filter JSON.")
            st.stop()

        df = pd.DataFrame(sorted(brand_totals.items()), columns=["Brand", "Count"]).reset_index(drop=True)

        st.success(f"Found {len(df)} unique brands! ✨")
        st.dataframe(df, use_container_width=True)

        # CSV download button
        csv_bytes = df.to_csv(index=False, encoding="utf-8").encode("utf-8")
        st.download_button(
            "Download CSV",
            data=csv_bytes,
            file_name="brand_counts.csv",
            mime="text/csv",
        )

# --- Footer -----------------------------------------------------------------------------
st.caption("Built with ❤ using Streamlit.")
