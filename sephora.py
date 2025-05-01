import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Brand Counter", layout="centered")

st.title("Brand & Count Extractor")
st.write(
    "Upload a product‑listing HTML file that contains a brand filter (e.g. Sephora, Level Shoes). The app parses the embedded JSON and returns **one row per brand** with its product total – no accidental doubles."
)

uploaded_file = st.file_uploader("Choose an HTML file", type=["html", "htm"])  # Accept .html & .htm

if uploaded_file is not None:
    html_text = uploaded_file.read().decode("utf-8", errors="ignore")

    # JSON fragment pattern: …\"hitCount\":123,\"label\":\"BRAND NAME\"…
    pattern = r'\\"hitCount\\":\s*(\d+),\\"label\\":\\"([^"\\]+)\\"'
    matches = re.findall(pattern, html_text)

    def looks_like_brand(label: str) -> bool:
        """Thin heuristic – adjust if your site uses mixed‑case labels, etc."""
        return (
            any(c.isalpha() for c in label)  # contains letters
            and not re.search(r'\d', label)  # no digits
            and not any(c.islower() for c in label)  # typically brands are all‑caps in this blob
        )

    # De‑duplicate **and** avoid double‑adding counts.
    # If a brand appears multiple times with the *same* count we ignore the extra;
    # if counts differ we keep the *max* (safer than a sum which would double‑up).
    brand_totals: dict[str, int] = {}
    for count_str, label in matches:
        if not looks_like_brand(label):
            continue
        count = int(count_str)
        if label not in brand_totals:
            brand_totals[label] = count
        else:
            # Keep whichever count is larger (handles desktop/mobile duplicate blocks).
            brand_totals[label] = max(brand_totals[label], count)

    if brand_totals:
        df = (
            pd.DataFrame(sorted(brand_totals.items()), columns=["Brand", "Count"])
            .reset_index(drop=True)
        )
        st.success(f"Found {len(df)} unique brands (deduplicated).")
        st.dataframe(df, use_container_width=True)

        # Provide download link
        csv_bytes = df.to_csv(index=False, encoding="utf-8").encode("utf-8")
        st.download_button(
            "Download CSV",
            data=csv_bytes,
            file_name="brand_counts.csv",
            mime="text/csv",
        )
    else:
        st.warning("No brands matched the detection rules. Verify the HTML file.")
else:
    st.info("Awaiting HTML upload …")
