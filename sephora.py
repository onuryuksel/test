import streamlit as st
import pandas as pd
import re
import json
from bs4 import BeautifulSoup
import io # String'i dosya benzeri bir nesneye dönüştürmek için

st.set_page_config(page_title="Sephora Marka Çıkarıcı", layout="wide")

st.title("💄 Sephora Marka Filtresi Veri Çıkarıcı")
st.write("Lütfen Sephora ürün listeleme sayfasının indirilmiş HTML dosyasını yükleyin.")
st.caption("Örnek dosya: 'Makeup Essentials_ Lips, Eyes & Skin ≡ Sephora.html'")

def extract_brands_from_html_content(html_content):
    """
    Parses HTML content string to find embedded brand filter data within a script tag,
    extracts brand names and their hit counts.

    Args:
        html_content (str): The HTML content as a string.

    Returns:
        tuple: A tuple containing (list of brand dictionaries, list of headers)
               or (None, None) if data extraction fails.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    scripts = soup.find_all('script')

    brands_data = []
    found_data = False
    fieldnames = ['Marka', 'Urun Adedi'] # CSV başlıkları

    # Regex to find the specific refinement block for brands
    pattern = re.compile(r'"attributeId"\s*:\s*"c_brand".*?"values"\s*:\s*(\[.*?\])', re.DOTALL)

    for script in scripts:
        if script.string:
            match = pattern.search(script.string)
            if match:
                json_like_string = match.group(1)
                try:
                    # Parse the captured JSON-like string
                    data_list = json.loads(json_like_string)
                    for item in data_list:
                        if isinstance(item, dict) and 'label' in item and 'hitCount' in item:
                            brands_data.append({
                                fieldnames[0]: item['label'], # 'Marka'
                                fieldnames[1]: item['hitCount'] # 'Urun Adedi'
                            })
                    found_data = True
                    break # Stop after finding the first match
                except json.JSONDecodeError as e:
                    st.warning(f"Script içinde JSON ayrıştırma hatası (göz ardı ediliyor): {e}\nVeri: {json_like_string[:100]}...")
                    continue # Try next script tag
                except Exception as e:
                    st.error(f"Veri işlenirken beklenmedik bir hata: {e}")
                    return None, None # Return None on critical error

    if not found_data or not brands_data:
        st.error("HTML içinde 'c_brand' attributeId'sine sahip marka filtresi verisi bulunamadı.")
        return None, None

    return brands_data, fieldnames

# --- Streamlit File Uploader ---
uploaded_file = st.file_uploader("HTML Dosyasını Buraya Sürükleyin veya Seçin", type=["html", "htm"])

if uploaded_file is not None:
    # Dosya içeriğini oku
    try:
        html_content = uploaded_file.getvalue().decode("utf-8")
        st.success(f"'{uploaded_file.name}' başarıyla yüklendi.")

        # Veriyi çıkar
        with st.spinner("Marka verileri çıkarılıyor..."):
            brands_data, headers = extract_brands_from_html_content(html_content)

        if brands_data and headers:
            st.success("Marka verileri başarıyla çıkarıldı!")

            # Veriyi DataFrame olarak göster
            df = pd.DataFrame(brands_data)
            st.dataframe(df, use_container_width=True)

            # CSV'ye dönüştür
            csv_string = df.to_csv(index=False, encoding='utf-8')

            # İndirme butonu
            st.download_button(
               label="CSV Olarak İndir",
               data=csv_string,
               file_name='sephora_markalar.csv',
               mime='text/csv',
            )
        # else: # Hata mesajı zaten extract_brands_from_html_content içinde veriliyor
            # st.error("Dosyadan marka verileri çıkarılamadı.")

    except UnicodeDecodeError:
        st.error("Dosya kodlaması UTF-8 değil gibi görünüyor. Lütfen UTF-8 formatında kaydedilmiş bir HTML dosyası yükleyin.")
    except Exception as e:
        st.error(f"Dosya işlenirken bir hata oluştu: {e}")
