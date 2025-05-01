import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
import re
import io
import json # JSON parse etmeyi denemek için

def extract_brand_filters_revised(html_content):
    """
    Parses the uploaded HTML content to extract brand filters and their counts,
    specifically targeting the structure found in the provided Sephora HTML.

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

        filter_data_str = None
        # Script etiketlerinde filtre tanımlarını içeren kısmı ara
        for script in scripts:
            # 'attributeId":"c_brand"' ve 'filters":[' anahtar kelimelerini içeren script'i bulmaya çalış
            if script.string and '"attributeId":"c_brand"' in script.string and '"filters":[' in script.string:
                 # 'filters' array'inin içeriğini doğrudan çıkarmayı dene
                 # filters array'inin başlangıcından kapanış köşeli parantezine kadar ara
                 match = re.search(r'"filters":\s*(\[.*?\])', script.string, re.DOTALL | re.IGNORECASE) # Boşlukları ve büyük/küçük harfi göz ardı et
                 if match:
                     filter_data_str = match.group(1)
                     # st.write("DEBUG: Found filters array string:") # Hata ayıklama için
                     # st.code(filter_data_str[:500] + "...", language='json') # İlk 500 karakteri göster
                     break # Bulunduysa döngüden çık

        if not filter_data_str:
            # Geriye dönük uyumluluk: self.__next_f içindeki veriyi ara (ilk deneme başarısız olursa)
            st.info("Initial filter search failed, trying fallback method...")
            for script in scripts:
                if script.string and 'self.__next_f.push([1,"' in script.string:
                    payload_match = re.search(r'self\.__next_f\.push\(\[1,"(.*)"\]\)', script.string, re.DOTALL)
                    if payload_match:
                        payload_str_escaped = payload_match.group(1)
                        # Temel kaçış karakteri temizleme (tüm durumları kapsamayabilir)
                        # JSON ayrıştırmasının hatasız çalışması için kaçış karakterlerini doğru şekilde ele almak önemlidir
                        try:
                           # JSON'un beklemediği bazı yapıları (örn. $L13) değiştirmeyi dene
                           # Bu kısım çok hassas olabilir ve sitenin yapısı değiştikçe güncellenmesi gerekebilir
                           payload_str_cleaned = payload_str_escaped.replace('\\\\"', "'").replace('\\"', '"').replace('\\\\', '\\').replace('\\n', '')
                           # $ ile başlayan referansları geçici olarak string yap
                           payload_str_cleaned = re.sub(r'":(\$[a-zA-Z0-9]+)([,}])', r'":"\1"\2', payload_str_cleaned)
                           payload_str_cleaned = re.sub(r'\[(\$[a-zA-Z0-9]+)\]', r'["\1"]', payload_str_cleaned) # $ ile başlayan array elemanları için

                           # Hata ayıklama için temizlenmiş stringin bir kısmını göster
                           # st.code(payload_str_cleaned[:1000]+"...", language='json')

                           filter_match = re.search(r'"filters":\s*(\[.*?\])', payload_str_cleaned, re.DOTALL | re.IGNORECASE)
                           if filter_match:
                               filter_data_str = filter_match.group(1)
                               # st.write("DEBUG: Found filters array string (Fallback):") # Hata ayıklama için
                               # st.code(filter_data_str[:500] + "...", language='json') # İlk 500 karakteri göster
                               break
                        except Exception as parse_err:
                           st.warning(f"Error cleaning/parsing fallback data: {parse_err}")
                           continue # Sonraki script'e geç
            
            if not filter_data_str:
                 st.warning("Could not locate the 'filters' array within any script tag using primary or fallback methods.")
                 return []


        # Çıkarılan filtreler string'i içinde spesifik marka filtresini bul
        # Daha esnek boşluk karakterleri için \s* kullanıldı
        # Değerler bölümünün doğrudan array [] olmasını bekleyen desen
        brand_filter_match = re.search(
            r'\{\s*"attributeId"\s*:\s*"c_brand"\s*,\s*"label"\s*:\s*"Brands"\s*,\s*"values"\s*:\s*(\[.*?\])\s*\}',
            filter_data_str,
            re.DOTALL | re.IGNORECASE
        )

        if not brand_filter_match:
            # Eğer doğrudan array bulunamazsa, $ ile başlayan referans formatını ara
            brand_filter_match_ref = re.search(
                 r'\{\s*"attributeId"\s*:\s*"c_brand"\s*,\s*"label"\s*:\s*"Brands"\s*,\s*"values"\s*:\s*"(\$\d+)"\s*\}',
                 filter_data_str,
                 re.DOTALL | re.IGNORECASE
            )
            if brand_filter_match_ref:
                ref_key = brand_filter_match_ref.group(1).replace("$","") # '$62' -> '62'
                st.info(f"Found brand filter reference key: ${ref_key}. Searching for its definition...")
                 # Şimdi referans anahtarının tanımını (örn. '62:[...]') tüm scriptlerde ara
                ref_definition_pattern = re.compile(rf'"{ref_key}":\s*(\[.*?\])', re.DOTALL) # Anahtarın tırnak içinde olduğunu varsay
                found_ref_def = False
                for script in scripts:
                    if script.string:
                         ref_def_match = ref_definition_pattern.search(script.string)
                         if ref_def_match:
                             brands_array_str_ref = ref_def_match.group(1)
                             # $ ile başlayan marka referanslarını ayıkla (örneğin "$63")
                             brand_key_matches = re.findall(r'"\$(\d+)"', brands_array_str_ref)
                             if not brand_key_matches:
                                  st.warning(f"Found reference definition for ${ref_key}, but could not extract individual brand keys (like '$63').")
                                  return []

                             # Şimdi her bir anahtarın ('63', '64', ...) tam tanımını ara
                             individual_brand_defs = {}
                             brand_def_pattern = re.compile(r'"(\d+)":\s*(\{\s*"hitCount"\s*:\s*(\d+)\s*,\s*"label"\s*:\s*"([^"]+)"\s*,\s*"value"\s*:\s*"[^"]+"\s*\})')
                             for script_inner in scripts:
                                 if script_inner.string:
                                     defs = brand_def_pattern.findall(script_inner.string)
                                     for key, full_def, count, label in defs:
                                         individual_brand_defs[key] = {'Brand': label.replace('\\"', '"').strip(), 'Count': int(count)}
                             
                             # Eşleşen anahtarları kullanarak veriyi oluştur
                             for key in brand_key_matches:
                                 if key in individual_brand_defs:
                                      brands_data.append(individual_brand_defs[key])
                                 else:
                                      st.warning(f"Definition for referenced brand key '{key}' not found.")
                             
                             found_ref_def = True
                             break # Referans tanımını bulduk, döngüden çık
                if not found_ref_def:
                    st.warning(f"Found brand filter reference key ${ref_key}, but couldn't find its definition array '[...]'.")
                    return []
            else:
                st.warning("Found 'filters' array, but couldn't find the specific 'c_brand' attribute structure (neither direct values nor reference value).")
                # Hata ayıklama için bulunan filtre verisini göster
                st.write("DEBUG: Searched within this filter data string:")
                st.code(filter_data_str[:1000] + "..."  if filter_data_str else "None", language='json')
                return []
        else:
             # Doğrudan values array'i bulunduysa, onu parse et
             brands_array_str = brand_filter_match.group(1)
             brand_entry_pattern = re.compile(r'\{\s*"hitCount"\s*:\s*(\d+)\s*,\s*"label"\s*:\s*"([^"]+)"\s*,\s*"value"\s*:\s*"[^"]+"\s*\}')
             brand_matches = brand_entry_pattern.findall(brands_array_str)
             if not brand_matches:
                 st.warning("Found the 'Brands' filter structure with direct values, but failed to parse individual brand entries.")
                 return []
             for count, label in brand_matches:
                 cleaned_label = label.replace('\\"', '"').strip() # Handle potential escaped quotes
                 brands_data.append({'Brand': cleaned_label, 'Count': int(count)})


        if not brands_data:
             st.warning("Data extraction process completed, but no brand data was ultimately collected.")
             return []

        # Alfabetik olarak sırala
        brands_data.sort(key=lambda x: x['Brand'])

    except Exception as e:
        st.error(f"An error occurred during HTML parsing: {e}")
        import traceback
        st.error(traceback.format_exc()) # Daha detaylı hata çıktısı için
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
    # Önce UTF-8 deneyelim, olmazsa başka encoding'leri deneyebiliriz
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

        st.dataframe(df, use_container_width=True)

        # DataFrame'i CSV string'ine dönüştür
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False, encoding='utf-8-sig') # utf-8-sig Excel uyumluluğu için daha iyi olabilir
        csv_string = csv_buffer.getvalue()

        # İndirme düğmesini göster
        st.download_button(
           label="Download Brand Data as CSV",
           data=csv_string,
           file_name='sephora_brands_filter.csv',
           mime='text/csv',
        )
    # Eğer extract_brand_filters_revised içinde zaten bir uyarı gösterildiyse tekrar gösterme
    elif 'streamlit_warning_shown' not in st.session_state:
         st.warning("No brand filter data found after processing. Ensure the HTML file is a complete Sephora PLP and contains the filter section data, possibly within `<script>` tags.")

# Reset warning state if file is removed or new one is uploaded
if 'warning_shown' in st.session_state and uploaded_file is None:
    del st.session_state['warning_shown']
