import streamlit as st
import pandas as pd
import re
from bs4 import BeautifulSoup  # Only needed if you prefer HTML parsing later
import io

st.set_page_config(page_title="Brand Counter", layout="centered")

st.title("Brand & Count Extractor")
st.write("Upload a product‑listing HTML file that contains a brand filter (like Sephora or Level Shoes). The app will parse the embedded data and give you a CSV of brands with product counts.")

uploaded_file = st.file_uploader("Choose an HTML file", type=["html", "htm"])  # Accepts .html or .htm

if uploaded_file is not None:
    # Read HTML
    html_text = uploaded_file.read().decode("utf-8", errors="ignore")

    # Regex pattern to capture \"hitCount\": <num>,\"label\":\"<BRAND>\"
    pattern = r'\\"hitCount\\":\s*(\d+),\\"label\\":\\"([^"\\]+)\\"'
    matches = re.findall(pattern, html_text)

    def looks_like_brand(label: str) -> bool:
        """Basic heuristic to weed out non‑brand labels."""
        return (
            any(c.isalpha() for c in label) and  # has letters
            not re.search(r'\d', label) and      # no digits
            not any(c.islower() for c in label)   # assume brands listed in full caps
        )

    # Build DataFrame
    data = [(label, int(count)) for count, label in matches if looks_like_brand(label)]
    if data:
        df = (
            pd.DataFrame(data, columns=["Brand", "Count"])  # type: ignore
            .sort_values("Brand")
            .reset_index(drop=True)
        )
        st.success(f"Found {len(df)} brands.")
        st.dataframe(df, use_container_width=True)

        # Offer download as CSV
        csv_bytes = df.to_csv(index=False, encoding="utf-8").encode("utf-8")
        st.download_button(
            label="Download CSV",
            data=csv_bytes,
            file_name="brand_counts.csv",
            mime="text/csv",
        )
    else:
        st.warning("No brands found. Make sure you uploaded the correct page.")
else:
    st.info("Awaiting HTML upload …")
