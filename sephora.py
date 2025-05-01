import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Brand Counter", layout="centered")

st.title("Brand & Count Extractor")
st.write(
    "Upload a product‑listing HTML file that contains a brand filter (e.g. Sephora, Level Shoes). The app will parse the embedded data and give you a single‑row‑per‑brand CSV."
)

uploaded_file = st.file_uploader("Choose an HTML file", type=["html", "htm"])  # Accept .html & .htm

if uploaded_file is not None:
    html_text = uploaded_file.read().decode("utf-8", errors="ignore")

    # Regex captures: …\"hitCount\":123,\"label\":\"BRAND NAME\"…
    pattern = r'\\"hitCount\\":\s*(\d+),\\"label\\":\\"([^"\\]+)\\"'
    matches = re.findall(pattern, html_text)

    def looks_like_brand(label: str) -> bool:
        """Very simple heuristic; adjust if needed."""
        return (
            any(c.isalpha() for c in label)  # has letters at all
            and not re.search(r'\d', label)  # exclude obvious SKU‑ish things
            and not any(c.islower() for c in label)  # most brand labels are uppercase in this JSON
        )

    # Aggregate counts — duplicate labels get summed once.
    brand_totals: dict[str, int] = {}
    for count_str, label in matches:
        if looks_like_brand(label):
            count = int(count_str)
            brand_totals[label] = brand_totals.get(label, 0) + count

    if brand_totals:
        df = (
            pd.DataFrame(sorted(brand_totals.items()), columns=["Brand", "Count"])
            .reset_index(drop=True)
        )
        st.success(f"Found {len(df)} unique brands.")
        st.dataframe(df, use_container_width=True)

        # Download as CSV
        csv_bytes = df.to_csv(index=False, encoding="utf-8").encode("utf-8")
        st.download_button(
            "Download CSV",
            data=csv_bytes,
            file_name="brand_counts.csv",
            mime="text/csv",
        )
    else:
        st.warning("No brands matched the detection rules. Make sure you uploaded the correct HTML page.")
else:
    st.info("Awaiting HTML upload …")
