import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
import re
import io
import traceback # Hata ayıklama için

# Session state'i kullanarak uyarıların tekrar tekrar gösterilmesini engelle
if 'warning_shown' not in st.session_state:
    st.session_state.warning_shown = False

def extract_brand_filters_from_payload(html_content):
    """
    Parses the uploaded HTML content by finding the main data payload
    (likely within self.__next_f.push) and extracting brand filters from it.

    Args:
        html_content (str): The HTML content as a string.

    Returns:
        list: A list of dictionaries, where each dictionary contains 'Brand' and 'Count'.
              Returns an empty list if no data is found or an error occurs.
    """
    st.session_state.warning_shown = False # Her yeni çalıştırmada uyarı durumunu sıfırla
    brands_data = []
    script_payload_raw = ""
    cleaned_payload = ""

    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        scripts = soup.find_all('script')

        # 1. Adım: self.__next_f.push([1,"..."]) içeren script'i bul ve payload'ı çıkar
        payload_found = False
        for script in scripts:
            if script.string and 'self.__next_f.push([1,"' in script.string:
                payload_match = re.search(r'self\.__next_f\.push\(\[1,"(.*)"\]\)', script.string, re.DOTALL | re.S)
                if payload_match:
                    script_payload_raw = payload_match.group(1)
                    payload_found = True
                    # st.write("DEBUG: Found self.__next_f.push payload.") # Hata ayıklama
                    break

        if not payload_found:
            st.warning("Could not find the 'self.__next_f.push([1,\"...\"])' script structure containing the page data.")
            st.session_state.warning_shown = True
            return []

        # 2. Adım: Payload string'ini temizle (kaçış karakterleri vb.)
        try:
            # Öncelik sırası önemli: Önce \\" sonra \" temizle
            cleaned_payload = script_payload_raw.replace('\\\\"', "'") # Çift kaçışlı tırnakları geçici olarak tek tırnak yap
            cleaned_payload = cleaned_payload.replace('\\"', '"')      # Tek kaçışlıları çift tırnak yap
            cleaned_payload = cleaned_payload.replace("'","\"")        # Geçici tek tırnakları çift tırnak yap (label'lar için)
            cleaned_payload = cleaned_payload.replace('\\n', ' ')     # Yeni satırları boşluk yap
            cleaned_payload = cleaned_payload.replace('\\\\', '\\')   # Çift ters eğik çizgiyi tek yap

            # JSON olmayan referansları ($ ile başlayan) string'e çevir (regex'lerin çalışması için kritik)
            # ":$XXX" -> ":\"$XXX\""
            cleaned_payload = re.sub(r':(\$L?[0-9a-zA-Z]+)([,}])', r':"\1"\2', cleaned_payload)
            # [$LXXX] -> ["$LXXX"]
            cleaned_payload = re.sub(r'\[(\$L?[0-9a-zA-Z]+)\]', r'["\1"]', cleaned_payload)

            # st.write("DEBUG: Cleaned Payload Snippet:") # Hata ayıklama
            # st.code(cleaned_payload[:1500] + "...", language='text')
        except Exception as clean_e:
             st.warning(f"Error during payload cleaning: {clean_e}. Proceeding with raw payload for regex.")
             st.session_state.warning_shown = True
             cleaned_payload = script_payload_raw # Temizleme başarısız olursa ham veriyle devam etmeyi dene

        # 3. Adım: Temizlenmiş payload içinde bireysel marka tanımlarını ("63":{"hitCount":..., "label":...}) bul
        individual_brand_defs = {}
        # Label içinde kaçış karakterlerini de yakalayacak şekilde güncellendi: ((?:[^"\\]|\\.)*)
        brand_def_pattern = re.compile(r'"(\d+)"\s*:\s*\{\s*"hitCount"\s*:\s*(\d+)\s*,\s*"label"\s*:\s*"((?:[^"\\]|\\.)*)"')
        all_defs = brand_def_pattern.findall(cleaned_payload)

        if not all_defs:
             st.warning("Found the data payload, but could not extract individual brand definitions (e.g., '63':{'hitCount':...}) using regex. The data format might be different or cleaning might have failed.")
             st.session_state.warning_shown = True
             return []
        # else:
        #      st.write(f"DEBUG: Found {len(all_defs)} potential brand definitions in the payload.") # Hata ayıklama

        for key, count, label in all_defs:
            # Temizlenmiş payload'da \\" kalmadığı için tekrar replace'e gerek yok
            individual_brand_defs[key] = {'Brand': label.strip(), 'Count': int(count)}

        # 4. Adım: "Brands" filtresinin referans anahtarını ("$62" gibi) temizlenmiş payload'da bul
        brand_filter_ref_key = None
        # Desen: "attributeId":"c_brand", ... "values":"$62"
        brand_filter_ref_pattern = re.compile(r'"attributeId"\s*:\s*"c_brand"\s*,\s*"label"\s*:\s*"Brands"\s*,\s*"values"\s*:\s*"\$(\d+)"')
        ref_match = brand_filter_ref_pattern.search(cleaned_payload)
        if ref_match:
            brand_filter_ref_key = ref_match.group(1) # Sadece sayısal kısmı ('62') al
            # st.write(f"DEBUG: Found brand filter reference key: ${brand_filter_ref_key}")
        else:
            st.warning("Could not find the 'Brands' filter definition structure with a reference value (e.g., 'values':'$62') within the data payload.")
            st.session_state.warning_shown = True
            return []

        # 5. Adım: Referans anahtarının tanımladığı array'i ("62":[...]) temizlenmiş payload'da bul
        brands_array_str = None
        brand_keys_in_array = []
        # Anahtarın tırnak içinde olduğunu varsayarak deseni oluştur: "62" : [...]
        ref_definition_pattern = re.compile(rf'"{brand_filter_ref_key}"\s*:\s*(\[.*?\])', re.DOTALL)
        def_match = ref_definition_pattern.search(cleaned_payload)
        if def_match:
            brands_array_str = def_match.group(1)
            # st.write(f"DEBUG: Found definition array for key {brand_filter_ref_key}.")
            # Array içindeki asıl marka anahtarlarını ("$63", "$64" -> "63", "64") çıkar
            brand_keys_in_array = re.findall(r'"\$(\d+)"', brands_array_str)
            if not brand_keys_in_array:
                 st.warning(f"Found the definition array for key {brand_filter_ref_key}, but failed to extract individual brand reference keys (e.g., '$63') from it.")
                 # st.code(brands_array_str, language='text') # Hata ayıklama
                 st.session_state.warning_shown = True
                 return []
            # else:
            #      st.write(f"DEBUG: Extracted {len(brand_keys_in_array)} brand keys: {brand_keys_in_array[:10]}...")
        else:
            st.warning(f"Found brand filter reference key ${brand_filter_ref_key}, but couldn't find its corresponding definition array '[\"...']' in the data payload.")
            st.session_state.warning_shown = True
            return []

        # 6. Adım: Çıkarılan anahtarları kullanarak marka verisini oluştur
        missing_keys_count = 0
        for key in brand_keys_in_array:
            if key in individual_brand_defs:
                brands_data.append(individual_brand_defs[key])
            else:
                missing_keys_count += 1
                # st.warning(f"DEBUG: Definition for referenced brand key '{key}' was not found.") # Hata ayıklama

        if missing_keys_count > 0:
             st.warning(f"{missing_keys_count} out of {len(brand_keys_in_array)} brand definitions could not be matched to their keys. The result might be incomplete.")
             st.session_state.warning_shown = True

        if not brands_data:
             st.warning("Successfully parsed the structure and keys, but couldn't match any keys to their definitions.")
             st.session_state.warning_shown = True
             return []

        # Alfabetik olarak sırala
        brands_data.sort(key=lambda x: x['Brand'])

    except Exception as e:
        st.error(f"An unexpected error occurred during processing: {e}")
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

uploaded_file = st.file_uploader("Choose a Sephora PLP HTML file", type=["html", "htm"])

if uploaded_file is not None:
    try:
        # Decode with potential fallback and ignoring errors
        string_data = uploaded_file.getvalue().decode("utf-8", errors='ignore')
    except Exception as e:
            st.error(f"Could not decode the uploaded file. Error: {e}")
            st.stop() # Stop processing if file cannot be read

    st.info("Processing uploaded HTML file...")
    extracted_data = extract_brand_filters_from_payload(string_data) # Yeni fonksiyonu çağır

    if extracted_data:
        st.success(f"Successfully extracted {len(extracted_data)} brands!")
        df = pd.DataFrame(extracted_data)
        # DataFrame'i gösterirken sütun sırasını kontrol et
        if 'Brand' in df.columns and 'Count' in df.columns:
            st.dataframe(df[['Brand', 'Count']], use_container_width=True) # Sütun sırasını zorla
        else:
             st.warning("Extracted data columns might be incorrect.")
             st.dataframe(df, use_container_width=True) # Orijinal haliyle göster

        # CSV oluşturma
        csv_buffer = io.StringIO()
        # Sütunların varlığını tekrar kontrol et
        if 'Brand' in df.columns and 'Count' in df.columns:
            df.to_csv(csv_buffer, index=False, columns=['Brand', 'Count'], encoding='utf-8-sig')
        else:
             df.to_csv(csv_buffer, index=False, encoding='utf-8-sig') # Orijinal sütunlarla yaz

        csv_string = csv_buffer.getvalue()

        st.download_button(
           label="Download Brand Data as CSV",
           data=csv_string,
           file_name='sephora_brands_filter.csv',
           mime='text/csv',
        )
    # Fonksiyon içinde zaten uyarı gösterilmediyse
    elif not st.session_state.warning_shown:
         st.warning("No brand filter data was ultimately extracted. Please ensure the uploaded file is a complete HTML source from a Sephora PLP page containing the necessary script data.")

# Reset warning state if file is removed
if uploaded_file is None and st.session_state.warning_shown:
    st.session_state.warning_shown = False
