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

def extract_brands_from_html_content(html_content):
    """
    Parses HTML content string to find embedded brand filter data within a script tag,
    extracts brand names and their hit counts using .get_text() and simplified regex.

    Args:
        html_content (str): The HTML content as a string.

    Returns:
        tuple: A tuple containing (list of brand dictionaries, list of headers)
               or (None, None) if data extraction fails.
    """
    soup = BeautifulSoup(html_content, 'lxml') # lxml parser'ı deneyelim
    scripts = soup.find_all('script')

    brands_data = []
    found_data = False
    fieldnames = ['Marka', 'Urun Adedi'] # CSV başlıkları

    # Basitleştirilmiş Regex: "attributeId":"c_brand" ifadesini ve onu takip eden
    # en yakın "values": [...] yapısını arar. İç içe yapıyı (?R) ile değil,
    # açgözlü olmayan .*? ile eşleştirir.
    pattern = re.compile(r'"attributeId"\s*:\s*"c_brand".*?"values"\s*:\s*(\[.*?\])', re.DOTALL)

    st.write(f"Toplam {len(scripts)} script etiketi bulundu.") # Bilgi

    for i, script in enumerate(scripts):
        script_content = script.get_text()
        if script_content:
            match = pattern.search(script_content)
            if match:
                st.info(f"Script #{i+1} içinde potansiyel 'c_brand' verisi bulundu.")
                json_like_string = match.group(1)
                # st.text(f"Yakalanan JSON string'i (ilk 150 karakter): {json_like_string[:150]}...")

                # JSON string'ini temizlemeye çalışalım (sondaki virgül vb.)
                json_like_string = json_like_string.strip()
                # Nadiren de olsa sonda virgül kalabilir
                if json_like_string.endswith(','):
                   json_like_string = json_like_string[:-1]
                   st.warning("JSON string'inin sonundaki fazladan virgül temizlendi.")

                try:
                    # JSON olarak ayrıştırmayı dene
                    data_list = json.loads(json_like_string)

                    if isinstance(data_list, list):
                        st.success(f"JSON başarıyla liste olarak ayrıştırıldı. {len(data_list)} potansiyel öğe bulundu.")
                        processed_count = 0
                        for item in data_list:
                            if isinstance(item, dict) and 'label' in item and 'hitCount' in item:
                                brands_data.append({
                                    fieldnames[0]: item['label'],
                                    fieldnames[1]: item['hitCount']
                                })
                                processed_count += 1
                            # else:
                            #     st.warning(f"Listede beklenen formatta olmayan öğe: {item}") # Çok fazla uyarı verebilir

                        if processed_count > 0:
                           st.success(f"{processed_count} adet marka/ürün sayısı başarıyla eklendi.")
                           found_data = True
                           break # Veri bulundu, döngüden çık
                        else:
                            st.warning("JSON listesi ayrıştırıldı ancak içinde geçerli marka öğesi bulunamadı.")
                    else:
                         st.warning(f"Regex eşleşti ancak ayrıştırılan veri bir liste değil: {type(data_list)}")

                except json.JSONDecodeError as e:
                    st.warning(f"Script #{i+1} içinde JSON ayrıştırma hatası: {e}. Veri başlangıcı: {json_like_string[:100]}...")
                except Exception as e:
                    st.error(f"Script #{i+1} işlenirken beklenmedik bir hata: {e}")

    if not found_data or not brands_data:
        st.error("HTML içinde 'c_brand' attributeId'sine sahip geçerli marka filtresi verisi bulunamadı. Lütfen HTML dosyasının doğru sayfanın tam kaynağı olduğundan ve verinin bir script etiketi içinde olduğundan emin olun.")
        return None, None

    return brands_data, fieldnames

# --- Streamlit File Uploader ---
uploaded_file = st.file_uploader("HTML Dosyasını Buraya Sürükleyin veya Seçin", type=["html", "htm"])

if uploaded_file is not None:
    try:
        # Dosyayı oku
        stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
        html_content = stringio.read()
        st.success(f"'{uploaded_file.name}' başarıyla yüklendi ve okundu.")

        with st.spinner("Marka verileri çıkarılıyor..."):
            brands_data, headers = extract_brands_from_html_content(html_content)

        if brands_data and headers:
            st.success("Marka verileri başarıyla çıkarıldı!")
            df = pd.DataFrame(brands_data)
            st.dataframe(df, use_container_width=True)
            csv_string = df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
               label="CSV Olarak İndir",
               data=csv_string,
               file_name='sephora_markalar.csv',
               mime='text/csv',
            )
        # else: # Hata mesajı zaten extract_brands_from_html_content içinde veriliyor
            # pass

    except UnicodeDecodeError:
        st.error("Dosya kodlaması UTF-8 değil gibi görünüyor. Lütfen UTF-8 formatında kaydedilmiş bir HTML dosyası yükleyin.")
    except Exception as e:
        st.error(f"Dosya işlenirken bir hata oluştu: {e}")
        st.exception(e) # Daha detaylı hata izi için
