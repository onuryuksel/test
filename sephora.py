import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
import re
import io
# import json # Bu sefer doğrudan JSON parse etmeye çalışmayacağız, regex kullanacağız

# Session state'i kullanarak uyarıların tekrar tekrar gösterilmesini engelle
if 'warning_shown' not in st.session_state:
    st.session_state.warning_shown = False

def extract_brand_filters_from_scripts(html_content):
    """
    Parses the uploaded HTML content to extract brand filters and their counts,
    specifically targeting the structure within <script> tags, likely inside self.__next_f.push.

    Args:
        html_content (str): The HTML content as a string.

    Returns:
        list: A list of dictionaries, where each dictionary contains 'Brand' and 'Count'.
              Returns an empty list if no data is found or an error occurs.
    """
    st.session_state.warning_shown = False # Her yeni çalıştırmada uyarı durumunu sıfırla
    brands_data = []
    relevant_script_content = ""

    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        scripts = soup.find_all('script')

        # 1. Adım: Marka filtresi verilerini içeren script bloğunu bul
        # Genellikle "attributeId":"c_brand" ve çok sayıda marka ismi içerir.
        # Performansı artırmak için önce ilgili olabilecek script'i bulmaya çalışalım.
        found_potential_script = False
        for script in scripts:
            if script.string and '"attributeId":"c_brand"' in script.string and '"label":"Brands"' in script.string:
                # Bu script muhtemelen filtre verilerini içeriyor
                relevant_script_content = script.string
                found_potential_script = True
                # st.write("DEBUG: Found potential script block containing 'c_brand'.") # Hata ayıklama
                break # İlk bulunanla devam edelim

        if not found_potential_script:
            st.warning("Could not find a script block containing the expected brand filter identifiers ('attributeId':'c_brand').")
            st.session_state.warning_shown = True
            return []

        # 2. Adım: Bireysel marka tanımlarını (örn: "63":{"hitCount":67,"label":"ANASTASIA BEVERLY HILLS", ...}) bul
        # Label içindeki kaçış karakterlerini (\") doğru yakalamak için `((?:[^"\\]|\\.)*)` kullanıldı
        individual_brand_defs = {}
        brand_def_pattern = re.compile(r'"(\d+)"\s*:\s*\{\s*"hitCount"\s*:\s*(\d+)\s*,\s*"label"\s*:\s*"((?:[^"\\]|\\.)*)"')
        all_defs = brand_def_pattern.findall(relevant_script_content)

        if not all_defs:
             st.warning("Found the script block, but could not extract individual brand definitions (e.g., '63':{'hitCount':...}) using regex. The data format within the script might be different.")
             # Hata ayıklama için scriptin bir kısmını göster
             # st.code(relevant_script_content[:1000] + "...", language='javascript')
             st.session_state.warning_shown = True
             return []
        # else:
        #      st.write(f"DEBUG: Found {len(all_defs)} potential brand definitions in the script.") # Hata ayıklama


        for key, count, label in all_defs:
            # Kaçış karakterlerini temizle
            cleaned_label = label.replace('\\"', '"').strip()
            individual_brand_defs[key] = {'Brand': cleaned_label, 'Count': int(count)}

        # 3. Adım: "Brands" filtresinin değerler listesini bul
        # Bu liste ya doğrudan marka anahtarlarını içerir ya da bir referans anahtarı içerir
        brands_array_str = None
        brand_keys_in_array = []

        # Önce doğrudan değer listesi formatını ara: "values":["$63","$64",...]
        direct_values_match = re.search(
            r'"attributeId"\s*:\s*"c_brand"\s*,\s*"label"\s*:\s*"Brands"\s*,\s*"values"\s*:\s*(\[.*?\])',
            relevant_script_content,
            re.DOTALL | re.IGNORECASE
        )

        if direct_values_match:
            brands_array_str = direct_values_match.group(1)
            # st.write("DEBUG: Found direct values array for brands.") # Hata ayıklama
            brand_keys_in_array = re.findall(r'"\$(\d+)"', brands_array_str) # $63 -> 63
        else:
            # Doğrudan liste yoksa, referans formatını ara: "values":"$62"
            ref_values_match = re.search(
                r'"attributeId"\s*:\s*"c_brand"\s*,\s*"label"\s*:\s*"Brands"\s*,\s*"values"\s*:\s*"\$(\d+)"',
                relevant_script_content,
                re.IGNORECASE
            )
            if ref_values_match:
                ref_key = ref_values_match.group(1) # '62'
                # st.write(f"DEBUG: Found reference key ${ref_key} for brands.") # Hata ayıklama
                # Şimdi bu referansın işaret ettiği array'i bul: "62":["$63","$64",...]
                ref_definition_pattern = re.compile(rf'"{ref_key}"\s*:\s*(\[.*?\])', re.DOTALL)
                def_match = ref_definition_pattern.search(relevant_script_content)
                if def_match:
                    brands_array_str = def_match.group(1)
                    # st.write(f"DEBUG: Found definition array for reference key {ref_key}.") # Hata ayıklama
                    brand_keys_in_array = re.findall(r'"\$(\d+)"', brands_array_str) # $63 -> 63
                else:
                    st.warning(f"Found brand filter reference key ${ref_key}, but couldn't find its corresponding definition array '[\"...']'.")
                    st.session_state.warning_shown = True
                    return []
            else:
                st.warning("Could not find the 'values' array or a reference key (e.g., '$62') for the 'Brands' filter.")
                st.session_state.warning_shown = True
                return []

        if not brand_keys_in_array:
            st.warning(f"Found the brand filter structure, but failed to extract individual brand keys (e.g., '$63') from the values list/reference.")
            # st.code(brands_array_str or "Values string not found", language='text') # Hata ayıklama
            st.session_state.warning_shown = True
            return []
        # else:
        #      st.write(f"DEBUG: Extracted {len(brand_keys_in_array)} brand keys: {brand_keys_in_array[:10]}...") # Hata ayıklama

        # 4. Adım: Çıkarılan anahtarları kullanarak ilk adımda bulunan tanımlardan veriyi oluştur
        missing_keys = 0
        for key in brand_keys_in_array:
            if key in individual_brand_defs:
                brands_data.append(individual_brand_defs[key])
            else:
                missing_keys += 1
                # st.warning(f"DEBUG: Definition for referenced brand key '{key}' was not found in the initial definition scan.") # Hata ayıklama

        if missing_keys > 0:
             st.warning(f"{missing_keys} brand definitions could not be matched to the extracted keys. The result might be incomplete.")
             st.session_state.warning_shown = True # Yine de uyarı gösterildi olarak işaretle

        if not brands_data:
             # Bu, anahtarların bulunduğu ancak hiçbirinin tanımının bulunmadığı anlamına gelir (çok olası değil)
             st.warning("Successfully parsed filter structure and keys, but couldn't match any keys to their definitions.")
             st.session_state.warning_shown = True
             return []

        # Alfabetik olarak sırala
        brands_data.sort(key=lambda x: x['Brand'])

    except Exception as e:
        st.error(f"An unexpected error occurred during HTML processing: {e}")
        import traceback
        st.error(traceback.format_exc()) # Daha detaylı hata çıktısı için
        st.session_state.warning_shown = True
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
    try:
        string_data = uploaded_file.getvalue().decode("utf-8")
    except UnicodeDecodeError:
        st.warning("UTF-8 decoding failed, trying 'latin-1'...")
        try:
            string_data = uploaded_file.getvalue().decode("latin-1")
        except Exception as e:
            st.error(f"Could not decode the uploaded file. Error: {e}")
            st.stop()

    st.info("Processing uploaded HTML file...")
    extracted_data = extract_brand_filters_from_scripts(string_data) # Yeni fonksiyonu çağır

    if extracted_data:
        st.success(f"Successfully extracted {len(extracted_data)} brands!")
        df = pd.DataFrame(extracted_data)
        st.dataframe(df, use_container_width=True)

        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
        csv_string = csv_buffer.getvalue()

        st.download_button(
           label="Download Brand Data as CSV",
           data=csv_string,
           file_name='sephora_brands_filter.csv',
           mime='text/csv',
        )
    elif not st.session_state.warning_shown: # Fonksiyon içinde zaten uyarı gösterilmediyse
         st.warning("No brand filter data found after processing. Ensure the HTML file is a complete Sephora PLP source and contains the filter section data within `<script>` tags.")

# Reset warning state if file is removed
if uploaded_file is None and st.session_state.warning_shown:
    st.session_state.warning_shown = False
