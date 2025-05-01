import streamlit as st
import pandas as pd
import re
import json
from bs4 import BeautifulSoup
import io

st.set_page_config(page_title="Sephora Marka Çıkarıcı", layout="wide")

st.title("💄 Sephora Marka Filtresi Veri Çıkarıcı")
st.write("Lütfen Sephora ürün listeleme sayfasının indirilmiş HTML dosyasını yükleyin.")
st.caption("Örnek dosya: 'Makeup Essentials_ Lips, Eyes & Skin ≡ Sephora.html'")

def find_brands_in_json(data):
    """Recursively search for the 'c_brand' attributeId within a parsed JSON object."""
    if isinstance(data, dict):
        # Doğrudan aradığımız yapıyı bulduk mu?
        if data.get("attributeId") == "c_brand" and "values" in data and isinstance(data["values"], list):
            return data["values"]
        # Değilse, sözlüğün değerlerini kontrol et
        for key, value in data.items():
            result = find_brands_in_json(value)
            if result is not None:
                return result
    elif isinstance(data, list):
        # Listenin her elemanını kontrol et
        for item in data:
            result = find_brands_in_json(item)
            if result is not None:
                return result
    # Bulunamadıysa None döndür
    return None

def extract_brands_from_scripts_robust(html_content):
    """
    Parses HTML content, finds scripts, attempts to parse them as JSON,
    and searches the JSON structure for the brand filter data.

    Args:
        html_content (str): The HTML content as a string.

    Returns:
        tuple: A tuple containing (list of brand dictionaries, list of headers)
               or (None, None) if data extraction fails.
    """
    try:
        soup = BeautifulSoup(html_content, 'lxml')
    except Exception as e:
        st.warning(f"lxml parser ile HTML ayrıştırılırken hata (html.parser deneniyor): {e}")
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
        except Exception as e2:
             st.error(f"HTML ayrıştırılamadı: {e2}")
             return None, None

    scripts = soup.find_all('script')
    brands_data = []
    found_data = False
    fieldnames = ['Marka', 'Urun Adedi']

    st.write(f"Toplam {len(scripts)} script etiketi bulundu ve JSON içeriği aranıyor...")
    processed_scripts = 0
    found_valid_json_scripts = 0

    for i, script in enumerate(scripts):
        script_content = script.get_text()
        if not script_content:
            continue

        processed_scripts += 1
        # Script içeriğinin JSON olup olmadığını anlamak için basit kontrol
        # Genellikle bu tür veriler { ... } veya [ ... ] ile başlar/biter.
        script_content_stripped = script_content.strip()
        if script_content_stripped.startswith(('{', '[')) and script_content_stripped.endswith(('}', ']')):
            # st.info(f"Script #{i+1} potansiyel JSON içeriyor, ayrıştırma deneniyor...") # Debug
            try:
                # JSON olarak ayrıştırmayı dene
                parsed_json = json.loads(script_content_stripped)
                found_valid_json_scripts += 1

                # Ayrıştırılan JSON içinde 'c_brand' verisini ara
                brand_values = find_brands_in_json(parsed_json)

                if brand_values is not None:
                    st.success(f"Script #{i+1} içinde 'c_brand' verisi bulundu!")
                    processed_count_in_script = 0
                    temp_brands_in_script = []
                    for item in brand_values:
                         if (isinstance(item, dict) and
                                'label' in item and isinstance(item['label'], str) and
                                'hitCount' in item and isinstance(item['hitCount'], int)):
                            temp_brands_in_script.append({
                                fieldnames[0]: item['label'],
                                fieldnames[1]: item['hitCount']
                            })
                            processed_count_in_script += 1

                    if processed_count_in_script > 0:
                       st.success(f"Script #{i+1}: {processed_count_in_script} adet geçerli marka/ürün sayısı bulundu ve eklendi.")
                       # Ana listeye ekle, yinelenenleri kontrol et
                       current_brand_labels = {d['Marka'] for d in brands_data}
                       new_brands_added = 0
                       for brand_entry in temp_brands_in_script:
                           if brand_entry['Marka'] not in current_brand_labels:
                               brands_data.append(brand_entry)
                               current_brand_labels.add(brand_entry['Marka'])
                               new_brands_added +=1
                       if new_brands_added > 0:
                           st.info(f"    -> {new_brands_added} yeni marka eklendi.")
                       found_data = True
                       # Genellikle tek bir yerde olacağı için bulunca durabiliriz
                       break
                    # else:
                       # st.warning(f"Script #{i+1}: 'c_brand' yapısı bulundu ancak 'values' listesi boş veya geçersiz öğeler içeriyor.")
                # else:
                    # st.write(f"Script #{i+1}: JSON ayrıştırıldı ancak 'c_brand' yapısı bulunamadı.") # Debug

            except json.JSONDecodeError:
                # st.warning(f"Script #{i+1} JSON'a benzese de ayrıştırılamadı.") # Debug
                pass # Hatalı JSON'ları sessizce geç
            except Exception as e:
                st.error(f"Script #{i+1} işlenirken beklenmedik bir hata: {e}")

        if found_data: # Veri bulunduysa diğer scriptleri kontrol etmeye gerek yok
            break

    st.info(f"Toplam {processed_scripts} script içeriği kontrol edildi, {found_valid_json_scripts} tanesi geçerli JSON olarak ayrıştırılabildi.")

    if not found_data:
        st.error("Tüm scriptler tarandı ancak 'c_brand' attributeId'sine ve geçerli 'values' listesine sahip beklenen veri yapısı bulunamadı.")
        st.warning("Olası Nedenler: \n - HTML dosyası eksik veya farklı bir sayfaya ait.\n - Veri yapısı tamamen değişmiş.\n - Veri, doğrudan script içinde değil, başka bir kaynaktan (API) yükleniyor olabilir.")
        return None, None

    # Yinelenenleri kaldır (gerçi break kullandığımız için gerekmeyebilir)
    unique_brands_data = []
    seen_brands = set()
    if brands_data:
        for brand_entry in brands_data:
            if isinstance(brand_entry, dict) and 'Marka' in brand_entry:
                if brand_entry['Marka'] not in seen_brands:
                    unique_brands_data.append(brand_entry)
                    seen_brands.add(brand_entry['Marka'])
            else:
                 st.warning(f"Marka listesinde beklenmeyen öğe tipi: {brand_entry}")

    st.info(f"Toplam {len(unique_brands_data)} benzersiz marka bulundu.")
    return unique_brands_data, fieldnames

# --- Streamlit File Uploader ---
uploaded_file = st.file_uploader("HTML Dosyasını Buraya Sürükleyin veya Seçin", type=["html", "htm"])

if uploaded_file is not None:
    try:
        stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
        html_content = stringio.read()
        st.success(f"'{uploaded_file.name}' başarıyla yüklendi ve okundu.")

        with st.spinner("Marka verileri çıkarılıyor..."):
            # Yeni fonksiyonu çağır
            brands_data, headers = extract_brands_from_scripts_robust(html_content)

        if brands_data and headers:
            st.success("Marka verileri başarıyla çıkarıldı!")
            df = pd.DataFrame(brands_data)
            df = df.sort_values(by='Marka').reset_index(drop=True)
            st.dataframe(df, use_container_width=True)
            csv_string = df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
               label="CSV Olarak İndir",
               data=csv_string,
               file_name='sephora_markalar.csv',
               mime='text/csv',
            )
        # else: # Hata mesajı fonksiyon içinde veriliyor.

    except UnicodeDecodeError:
        st.error("Dosya kodlaması UTF-8 değil gibi görünüyor. Lütfen UTF-8 formatında kaydedilmiş bir HTML dosyası yükleyin.")
    except Exception as e:
        st.error(f"Dosya işlenirken genel bir hata oluştu: {e}")
        st.exception(e)
