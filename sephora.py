import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
import re
import io

def extract_brand_filters(html_content):
    """
    Parses the uploaded HTML content to extract brand filters and their counts.

    Args:
        html_content (str): The HTML content as a string.

    Returns:
        list: A list of dictionaries, where each dictionary contains 'Brand' and 'Count'.
              Returns an empty list if no data is found or an error occurs.
    """
    brands_data = []
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        scripts = soup.find_all('script')
        
        # Regex to find the JSON-like definitions for brands (e.g., 63:{"hitCount":67,"label":"ANASTASIA BEVERLY HILLS",...})
        # This pattern looks for a number followed by a colon, then a JSON object containing "hitCount" and "label"
        # It assumes the structure observed in the example HTML's script tags.
        brand_pattern = re.compile(r'(\d+):\{"hitCount":(\d+),"label":"([^"]+)",') # Simpler pattern focusing on numeric key

        # Data structure to hold potential brand definitions found across scripts
        potential_brands = {}
        
        # 1. Find all potential brand definitions keyed by number
        for script in scripts:
            if script.string:
                matches = brand_pattern.findall(script.string)
                for key, count, label in matches:
                   # Clean up label (remove potential escape characters if necessary, though unlikely here)
                   cleaned_label = label.replace('\\"', '"').strip()
                   # Store with numeric key
                   potential_brands[key] = {'Brand': cleaned_label, 'Count': int(count)}

        # 2. Find the script section defining the actual 'Brands' filter and its value references
        brand_filter_found = False
        target_key_prefix = None # Will store the prefix like '$' if found
        brand_keys = []

        # More specific regex to find the 'Brands' filter structure
        # Looks for "attributeId":"c_brand","label":"Brands","values":"$[...]"
        # Captures the prefix before the references (e.g., '$') and the list of references
        filter_pattern = re.compile(r'"attributeId":"c_brand","label":"Brands","values":("\$([a-zA-Z0-9]+)"|\[([^\]]+)\])')

        for script in scripts:
            if script.string:
                filter_match = filter_pattern.search(script.string)
                if filter_match:
                    brand_filter_found = True
                    # Check which group captured the values list
                    if filter_match.group(2): # Single reference like "$XXX"
                         target_key_prefix = filter_match.group(1) # The '$'
                         # This case needs refinement if it occurs, as it wasn't in the example's primary list
                         st.warning("Found single reference format for brands, extraction might be incomplete.")
                         # Attempt to handle (assuming the single ref points to another structure - unlikely for brands)
                         # brand_keys = [filter_match.group(2)] # Example: ['62'] if format was "$62"
                    elif filter_match.group(3): # Array reference like ["$63","$64",...]
                        values_str = filter_match.group(3)
                        # Extract keys from the array string e.g., '"$63","$64"' -> ['63', '64']
                        # Extract the prefix ($) and the keys (numbers)
                        key_matches = re.findall(r'"(\$?)(\d+)"', values_str)
                        if key_matches:
                           target_key_prefix = key_matches[0][0] # Get the prefix ('$') from the first match
                           brand_keys = [match[1] for match in key_matches] # Get the numeric keys ['63', '64', ...]
                    break # Stop after finding the first match

        if not brand_filter_found:
            st.warning("Could not find the 'Brands' filter definition structure in the scripts.")
            return []
            
        if not brand_keys:
            st.warning("Found 'Brands' filter structure, but couldn't extract brand key references.")
            return []

        # 3. Look up the extracted keys in the potential_brands dictionary
        for key in brand_keys:
            if key in potential_brands:
                brands_data.append(potential_brands[key])
            else:
                # This might happen if the definition is in a different script block not yet processed
                # or if the initial regex missed some definitions.
                print(f"Warning: Definition for brand key '{key}' not found.")


        # Sort alphabetically by Brand name
        brands_data.sort(key=lambda x: x['Brand'])

    except Exception as e:
        st.error(f"An error occurred during HTML parsing: {e}")
        return []

    return brands_data

# --- Streamlit App UI ---
st.set_page_config(layout="wide")
st.title("🛍️ Sephora PLP Brand Filter Extractor")

st.write("""
Upload an HTML file saved directly from a Sephora Product Listing Page (PLP) 
(e.g., Makeup, Skincare categories). This app will attempt to extract the 
'Brands' filter data and provide it as a downloadable CSV file.
""")

uploaded_file = st.file_uploader("Choose a Sephora PLP HTML file", type="html")

if uploaded_file is not None:
    # To read file as string:
    string_data = uploaded_file.getvalue().decode("utf-8")
    
    st.info("Processing uploaded HTML file...")
    
    extracted_data = extract_brand_filters(string_data)
    
    if extracted_data:
        st.success(f"Successfully extracted {len(extracted_data)} brands!")
        
        # Create Pandas DataFrame
        df = pd.DataFrame(extracted_data)
        
        st.dataframe(df, use_container_width=True)
        
        # Convert DataFrame to CSV string
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False, encoding='utf-8')
        csv_string = csv_buffer.getvalue()
        
        # Provide download button
        st.download_button(
           label="Download Brand Data as CSV",
           data=csv_string,
           file_name='sephora_brands_filter.csv',
           mime='text/csv',
        )
    elif not extracted_data and "Could not find" not in st.session_state.get('warning_message', ''): 
        # Only show this if no specific warning was already given by the extraction function
         st.warning("No brand filter data found. Ensure the HTML file is a Sephora PLP and contains the filter section data, possibly within `<script>` tags.")
         st.session_state.warning_message = "No brand filter data found" # Store to avoid redundant messages if applicable
    # else: an error message was already displayed by the function

# Clear warning message state if no file is uploaded
if uploaded_file is None and 'warning_message' in st.session_state:
    del st.session_state['warning_message']
