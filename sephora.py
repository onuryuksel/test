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
    Parses HTML content string to find embedded brand filter data within script tags,
    extracts brand names and their hit counts. Checks ALL script tags.

    Args:
        html_content (str): The HTML content as a string.

    Returns:
        tuple: A tuple containing (list of brand dictionaries, list of headers)
               or (None, None) if data extraction fails.
    """
    try:
        soup = BeautifulSoup(html_content, 'lxml')
        scripts = soup.find_all('script')
    except Exception as e:
        st.error(f"HTML ayrıştırılırken hata oluştu (lxml): {e}")
        st.info("Standart 'html.parser' ile tekrar deneniyor...")
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            scripts = soup.find_all('script')
        except Exception as e2:
            st.error(f"HTML ayrıştırılırken tekrar hata oluştu (html.parser): {e2}")
            return None, None

    brands_data = []
    found_potential_match = False # Eşleşme olup olmadığını takip etmek için
    fieldnames = ['Marka', 'Urun Adedi'] # CSV başlıkları

    pattern = re.compile(r'"attributeId"\s*:\s*"c_brand".*?"values"\s*:\s*(\[.*?\])', re.DOTALL)

    st.write(f"Toplam {len(scripts)} script etiketi bulundu ve kontrol ediliyor...")

    for i, script in enumerate(scripts):
        script_content = script.get_text()
        if script_content:
            match = pattern.search(script_content)
            if match:
                found_potential_match = True # En az bir script'te desen bulundu
                st.info(f"Script #{i+1} içinde potansiyel 'c_brand' verisi bulundu.")
                json_like_string = match.group(1)

                # JSON string'ini temizlemeye çalışalım
                json_like_string = json_like_string.strip()
                if json_like_string.endswith(','):
                   json_like_string = json_like_string[:-1]

                try:
                    data_list = json.loads(json_like_string)

                    if isinstance(data_list, list) and data_list:
                        processed_count_in_script = 0
                        for item in data_list:
                            # Veri yapısını daha dikkatli kontrol edelim
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
                           # Artık tüm geçerli verileri topladığımız için burada durabiliriz,
                           # çünkü genellikle bu veri tek bir yerde bulunur.
                           # Ancak garanti olması için break koymayalım, belki başka yerde de vardır.
                           # found_data = True # Eğer sadece ilk bulduğu yerde dursun istiyorsak bunu açıp break ekleyebiliriz
                           # break
                        # else:
                           # st.warning(f"Script #{i+1}: JSON listesi ayrıştırıldı ancak içinde geçerli marka öğesi bulunamadı.")
                    # else:
                         # st.warning(f"Script #{i+1}: Regex eşleşti ancak ayrıştırılan veri beklenen liste formatında değil veya boş.")

                except json.JSONDecodeError as e:
                    st.warning(f"Script #{i+1} içinde JSON ayrıştırma hatası: {e}. Veri başlangıcı: {json_like_string[:100]}...")
                except Exception as e:
                    st.error(f"Script #{i+1} işlenirken beklenmedik bir hata: {e}")

    if not brands_data: # Eğer döngü bittiğinde hiç veri eklenmemişse
        if found_potential_match:
            st.error("Desenle eşleşen script(ler) bulundu ancak içlerinden geçerli marka verisi (label/hitCount içeren liste) çıkarılamadı. Script içeriği beklenenden farklı olabilir.")
        else:
            st.error("HTML içinde 'c_brand' attributeId'sine sahip marka filtresi deseni içeren hiçbir script etiketi bulunamadı.")
        return None, None

    # Yinelenenleri (eğer varsa) kaldır
    unique_brands_data = []
    seen_brands = set()
    for brand_entry in brands_data:
        if brand_entry['Marka'] not in seen_brands:
            unique_brands_data.append(brand_entry)
            seen_brands.add(brand_entry['Marka'])

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
            csv_string = df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
               label="CSV Olarak İndir",
               data=csv_string,
               file_name='sephora_markalar.csv',
               mime='text/csv',
            )
        # Hata mesajları artık fonksiyon içinde veriliyor.

    except UnicodeDecodeError:
        st.error("Dosya kodlaması UTF-8 değil gibi görünüyor. Lütfen UTF-8 formatında kaydedilmiş bir HTML dosyası yükleyin.")
    except Exception as e:
        st.error(f"Dosya işlenirken genel bir hata oluştu: {e}")
        st.exception(e)
