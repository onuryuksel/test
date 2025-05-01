import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
import re
import io
import json # Güvenlik için ve potansiyel JSON parse denemeleri için

# Session state'i kullanarak uyarıların tekrar tekrar gösterilmesini engelle
if 'warning_shown' not in st.session_state:
    st.session_state.warning_shown = False

def extract_brand_filters_revised(html_content):
    """
    Parses the uploaded HTML content to extract brand filters and their counts,
    specifically targeting the multi-step reference structure found in the provided Sephora HTML.

    Args:
        html_content (str): The HTML content as a string.

    Returns:
        list: A list of dictionaries, where each dictionary contains 'Brand' and 'Count'.
              Returns an empty list if no data is found or an error occurs.
    """
    st.session_state.warning_shown = False # Her yeni çalıştırmada uyarı durumunu sıfırla
    brands_data = []
    all_script_content = ""

    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        scripts = soup.find_all('script')

        # Performansı artırmak için tüm script içeriklerini birleştir
        for script in scripts:
            if script.string:
                all_script_content += script.string + "\n"

        # 1. Adım: Tüm potansiyel marka tanımlarını (örn: "63":{...}) bul ve sakla
        individual_brand_defs = {}
        # Daha spesifik olarak "hitCount" ve "label" içeren objeleri ara
        # Regex: "SAYI": { "hitCount": SAYI, "label": "MARKAISMI" ... }
        brand_def_pattern = re.compile(r'"(\d+)"\s*:\s*\{\s*"hitCount"\s*:\s*(\d+)\s*,\s*"label"\s*:\s*"((?:[^"\\]|\\.)*)"') # Label içinde kaçış karakterlerini de yakala
        all_defs = brand_def_pattern.findall(all_script_content)
        for key, count, label in all_defs:
            # Label'daki olası kaçış karakterlerini temizle (örn: \")
            cleaned_label = label.replace('\\"', '"').strip()
            individual_brand_defs[key] = {'Brand': cleaned_label, 'Count': int(count)}

        if not individual_brand_defs:
             st.warning("Could not find any individual brand definitions (e.g., '63':{'hitCount':...}). The HTML structure might have changed.")
             st.session_state.warning_shown = True
             return []
        # else:
        #      st.write(f"DEBUG: Found {len(individual_brand_defs)} potential brand definitions.") # Hata ayıklama

        # 2. Adım: "Brands" filtresinin referans anahtarını ("$62" gibi) bul
        brand_filter_ref_key = None
        brand_filter_ref_pattern = re.compile(r'"attributeId"\s*:\s*"c_brand"\s*,\s*"label"\s*:\s*"Brands"\s*,\s*"values"\s*:\s*"\$(\d+)"')
        ref_match = brand_filter_ref_pattern.search(all_script_content)
        if ref_match:
            brand_filter_ref_key = ref_match.group(1) # Sadece sayısal kısmı ('62') al
            # st.write(f"DEBUG: Found brand filter reference key: ${brand_filter_ref_key}") # Hata ayıklama
        else:
            st.warning("Could not find the 'Brands' filter definition structure with a reference value (e.g., 'values':'$62').")
            st.session_state.warning_shown = True
            return []

        # 3. Adım: Referans anahtarının tanımladığı array'i ("62":[...]) bul
        brands_array_str = None
        # Anahtarın tırnak içinde olduğunu varsayarak deseni oluştur
        ref_definition_pattern = re.compile(rf'"{brand_filter_ref_key}"\s*:\s*(\[.*?\])', re.DOTALL)
        def_match = ref_definition_pattern.search(all_script_content)
        if def_match:
            brands_array_str = def_match.group(1)
            # st.write(f"DEBUG: Found definition array for key {brand_filter_ref_key}:") # Hata ayıklama
            # st.code(brands_array_str[:200] + "...", language='text') # Hata ayıklama
        else:
            st.warning(f"Found brand filter reference key ${brand_filter_ref_key}, but couldn't find its corresponding definition array '[...]' in the scripts.")
            st.session_state.warning_shown = True
            return []

        # 4. Adım: Array içindeki asıl marka anahtarlarını ("$63", "$64" -> "63", "64") çıkar
        brand_keys_in_array = re.findall(r'"\$(\d+)"', brands_array_str)
        if not brand_keys_in_array:
            st.warning(f"Found the definition array for key {brand_filter_ref_key}, but failed to extract individual brand reference keys (e.g., '$63') from it.")
            st.code(brands_array_str, language='text') # Hata ayıklama için array'i göster
            st.session_state.warning_shown = True
            return []
        # else:
        #      st.write(f"DEBUG: Extracted {len(brand_keys_in_array)} brand keys from reference array.") # Hata ayıklama


        # 5. Adım: Çıkarılan anahtarları kullanarak ilk adımda bulunan tanımlardan veriyi oluştur
        for key in brand_keys_in_array:
            if key in individual_brand_defs:
                brands_data.append(individual_brand_defs[key])
            else:
                # Bu nadir olmalı, eğer ilk adım tüm tanımları bulduysa
                st.warning(f"Definition for referenced brand key '{key}' was expected but not found in the initial scan.")
                st.session_state.warning_shown = True


        if not brands_data:
             # Bu noktada anahtarlar bulunduysa ama tanımlar eşleşmediyse bu uyarı gösterilir.
             st.warning("Successfully parsed filter structure but couldn't match extracted brand keys to their definitions.")
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
    # Dosyayı string olarak oku:
    try:
        string_data = uploaded_file.getvalue().decode("utf-8")
    except UnicodeDecodeError:
        st.warning("UTF-8 decoding failed, trying 'latin-1'...")
        try:
            string_data = uploaded_file.getvalue().decode("latin-1")
        except Exception as e:
            st.error(f"Could not decode the uploaded file. Error: {e}")
            st.stop() # Hata durumunda devam etme


    st.info("Processing uploaded HTML file...")

    # Güncellenmiş fonksiyonu çağır
    extracted_data = extract_brand_filters_revised(string_data)

    if extracted_data:
        st.success(f"Successfully extracted {len(extracted_data)} brands!")

        # Pandas DataFrame oluştur
        df = pd.DataFrame(extracted_data)

        # Sütun adlarını doğrula (Brand, Count olmalı)
        if list(df.columns) != ['Brand', 'Count']:
             st.warning(f"Warning: DataFrame columns are not as expected: {list(df.columns)}. Adjusting...")
             # Gerekirse yeniden adlandırma yapılabilir, ama extract fonksiyonu doğruysa buna gerek kalmamalı.
             # df.columns = ['Brand', 'Count']

        st.dataframe(df, use_container_width=True)

        # DataFrame'i CSV string'ine dönüştür
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False, encoding='utf-8-sig') # Excel uyumluluğu için
        csv_string = csv_buffer.getvalue()

        # İndirme düğmesini göster
        st.download_button(
           label="Download Brand Data as CSV",
           data=csv_string,
           file_name='sephora_brands_filter.csv',
           mime='text/csv',
        )
    # Eğer extract_brand_filters_revised içinde zaten bir uyarı gösterildiyse tekrar gösterme
    elif not st.session_state.warning_shown:
         st.warning("No brand filter data was ultimately extracted. Please ensure the uploaded file is a complete HTML source from a Sephora PLP page containing the brand filter information.")

# Reset warning state if file is removed
if uploaded_file is None and st.session_state.warning_shown:
    st.session_state.warning_shown = False
