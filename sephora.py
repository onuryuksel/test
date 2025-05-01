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
    Parses HTML content string to find embedded brand filter data within script tags,
    extracts brand names and their hit counts. Checks ALL script tags and provides debug info.

    Args:
        html_content (str): The HTML content as a string.

    Returns:
        tuple: A tuple containing (list of brand dictionaries, list of headers)
               or (None, None) if data extraction fails.
    """
    try:
        # lxml daha toleranslı olabilir, eğer kurulu değilse 'html.parser' kullanılabilir.
        # pip install lxml
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
    found_potential_match_script = False # Desen içeren script bulundu mu?
    fieldnames = ['Marka', 'Urun Adedi'] # CSV başlıkları

    # attributeId:"c_brand" ve ardından gelen ilk "values": [...] yapısını arayan regex
    # JSON içindeki tırnaklar için kaçış karakterlerini de (\") hesaba katmaya çalışır.
    # .*? ile açgözlü olmayan eşleştirme yapılır.
    pattern = re.compile(r'"attributeId"\s*:\s*"c_brand".*?"values"\s*:\s*(\[.*?\])', re.DOTALL)

    st.write(f"Toplam {len(scripts)} script etiketi bulundu ve kontrol ediliyor...")
    relevant_scripts_content = [] # İlgili olabilecek script içeriklerini sakla

    for i, script in enumerate(scripts):
        # script.string yerine get_text() daha güvenilir olabilir
        script_content = script.get_text()
        if script_content:
            # Önce anahtar kelimelerin varlığını kontrol et, regex'i boşuna çalıştırma
            if '"attributeId"' in script_content and '"c_brand"' in script_content and '"values"' in script_content:
                # Potansiyel script bulundu, içeriği debug için sakla
                relevant_scripts_content.append(f"--- Script #{i+1} (Potansiyel 'c_brand' İçeriyor) ---\n{script_content[:1500]}...\n----------------------------------------\n") # Daha uzun bir parça alalım
                found_potential_match_script = True

                match = pattern.search(script_content)
                if match:
                    st.info(f"Script #{i+1} içinde regex deseni eşleşti!")
                    json_like_string = match.group(1)
                    json_like_string = json_like_string.strip()
                    # Sondaki virgülü temizle (bazen JSON hatalarına yol açar)
                    if json_like_string.endswith(','):
                       json_like_string = json_like_string[:-1]

                    try:
                        # JSON olarak ayrıştır
                        data_list = json.loads(json_like_string)

                        if isinstance(data_list, list):
                            st.success(f"Script #{i+1}: JSON başarıyla liste olarak ayrıştırıldı ({len(data_list)} öğe).")
                            processed_count_in_script = 0
                            for item in data_list:
                                # Veri yapısını doğrula
                                if (isinstance(item, dict) and
                                        'label' in item and isinstance(item['label'], str) and
                                        'hitCount' in item and isinstance(item['hitCount'], int)):
                                    brands_data.append({
                                        fieldnames[0]: item['label'],
                                        fieldnames[1]: item['hitCount']
                                    })
                                    processed_count_in_script += 1

                            if processed_count_in_script > 0:
                               st.success(f"Script #{i+1}: {processed_count_in_script} adet geçerli marka/ürün sayısı bulundu ve eklendi.")
                               found_data = True
                               # break # İlk başarılı bulmadan sonra durmak isterseniz bu satırı açın
                            # else:
                                # st.warning(f"Script #{i+1}: JSON listesi ayrıştırıldı ancak içinde geçerli marka öğesi bulunamadı.")
                        # else:
                             # st.warning(f"Script #{i+1}: Regex eşleşti ancak ayrıştırılan veri bir liste değil: {type(data_list)}")

                    except json.JSONDecodeError as e:
                        st.warning(f"Script #{i+1} içinde JSON ayrıştırma hatası: {e}. Veri başlangıcı: {json_like_string[:200]}...")
                    except Exception as e:
                        st.error(f"Script #{i+1} işlenirken beklenmedik bir hata: {e}")
                # else:
                    # st.write(f"Script #{i+1}: Anahtar kelimeler var ama regex deseni tam eşleşmedi.") # Debug

    if not found_data:
        st.error("HTML içinde geçerli marka filtresi verisi bulunamadı.")
        if found_potential_match_script:
            st.warning("Ancak, 'attributeId', 'c_brand' ve 'values' anahtar kelimelerini içeren şu script(ler) bulundu. Lütfen içeriklerini inceleyerek verinin yapısını kontrol edin veya regex desenini buna göre ayarlayın:")
            with st.expander("Potansiyel Olarak İlgili Script İçerikleri (İlk 1500 Karakter)"):
                if relevant_scripts_content:
                    for content in relevant_scripts_content:
                        st.code(content, language='javascript')
                else: # Bu durum aslında yaşanmamalı ama bir kontrol
                    st.write("İlgili script içeriği bulunamadı (beklenmedik durum).")
        else:
            st.warning("'attributeId', 'c_brand' ve 'values' anahtar kelimelerini içeren hiçbir script bulunamadı. HTML kaynağını kontrol edin.")
        return None, None

    # Yinelenenleri kaldır (eğer break kullanılmadıysa)
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
            brands_data, headers = extract_brands_from_html_content(html_content)

        if brands_data and headers:
            st.success("Marka verileri başarıyla çıkarıldı!")
            df = pd.DataFrame(brands_data)
            st.dataframe(df, use_container_width=True)
            csv_string = df.to_csv(index=False, encoding='utf-8-sig') # Excel uyumluluğu için utf-8-sig
            st.download_button(
               label="CSV Olarak İndir",
               data=csv_string,
               file_name='sephora_markalar.csv',
               mime='text/csv',
            )
        # Hata mesajı zaten extract_brands_from_html_content içinde veriliyor

    except UnicodeDecodeError:
        st.error("Dosya kodlaması UTF-8 değil gibi görünüyor. Lütfen UTF-8 formatında kaydedilmiş bir HTML dosyası yükleyin.")
    except Exception as e:
        st.error(f"Dosya işlenirken genel bir hata oluştu: {e}")
        st.exception(e) # Hatayı konsola ve ekrana daha detaylı yazdır
