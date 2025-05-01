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
    extracts brand names and their hit counts using .get_text() for robustness.

    Args:
        html_content (str): The HTML content as a string.

    Returns:
        tuple: A tuple containing (list of brand dictionaries, list of headers)
               or (None, None) if data extraction fails.
    """
    soup = BeautifulSoup(html_content, 'lxml') # Daha güçlü bir parser deneyelim: lxml
    # Eğer lxml kurulu değilse veya sorun çıkarırsa 'html.parser' kullanabilirsiniz:
    # soup = BeautifulSoup(html_content, 'html.parser')
    scripts = soup.find_all('script')

    brands_data = []
    found_data = False
    fieldnames = ['Marka', 'Urun Adedi'] # CSV başlıkları

    # Regex: "attributeId":"c_brand" ifadesini ve onu takip eden en yakın "values": [...] yapısını arar.
    # JSON içindeki tırnak işaretleri için kaçış karakterlerini de (\") dikkate alır.
    pattern = re.compile(r'"attributeId"\s*:\s*"c_brand".*?"values"\s*:\s*(\[(?:[^\[\]]|(?R))*?\])', re.DOTALL)
    # (?R) recursive pattern anlamına gelir, iç içe geçmiş [] yapılarını da eşleştirmeye çalışır.

    st.write(f"Toplam {len(scripts)} script etiketi bulundu.") # Bilgi

    for i, script in enumerate(scripts):
        # script.string yerine get_text() kullanarak içeriği daha güvenilir alalım
        script_content = script.get_text()
        if script_content:
            # İçeriğin küçük bir kısmını debug için yazdırabiliriz
            # st.text(f"Script #{i+1} içeriği (ilk 300 karakter):\n{script_content[:300]}\n---")

            match = pattern.search(script_content)
            if match:
                st.info(f"Script #{i+1} içinde potansiyel 'c_brand' verisi bulundu.")
                json_like_string = match.group(1)
                # st.text(f"Yakalanan JSON string'i (ilk 150 karakter): {json_like_string[:150]}...")

                # Bazen JSON string'inin sonunda fazladan virgül olabilir, temizleyelim
                json_like_string = json_like_string.strip()
                if json_like_string.endswith(','):
                   json_like_string = json_like_string[:-1]

                try:
                    # JSON olarak ayrıştırmayı dene
                    data_list = json.loads(json_like_string)

                    if isinstance(data_list, list):
                        st.success(f"JSON başarıyla liste olarak ayrıştırıldı. {len(data_list)} öğe bulundu.")
                        processed_count = 0
                        for item in data_list:
                            if isinstance(item, dict) and 'label' in item and 'hitCount' in item:
                                brands_data.append({
                                    fieldnames[0]: item['label'],
                                    fieldnames[1]: item['hitCount']
                                })
                                processed_count += 1
                            # else:
                                # st.warning(f"Listede beklenen formatta olmayan öğe: {item}")

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
                    # return None, None # Kritik hatada durdurabiliriz

    if not found_data or not brands_data:
        st.error("HTML içinde 'c_brand' attributeId'sine sahip geçerli marka filtresi verisi bulunamadı. Lütfen HTML dosyasının doğru sayfanın tam kaynağı olduğundan ve verinin bir script etiketi içinde olduğundan emin olun.")
        return None, None

    return brands_data, fieldnames

# --- Streamlit File Uploader ---
uploaded_file = st.file_uploader("HTML Dosyasını Buraya Sürükleyin veya Seçin", type=["html", "htm"])

if uploaded_file is not None:
    try:
        # Dosyayı Streamlit'in önerdiği şekilde işle
        stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
        html_content = stringio.read()
        st.success(f"'{uploaded_file.name}' başarıyla yüklendi ve okundu.")

        with st.spinner("Marka verileri çıkarılıyor..."):
            brands_data, headers = extract_brands_from_html_content(html_content)

        if brands_data and headers:
            st.success("Marka verileri başarıyla çıkarıldı!")
            df = pd.DataFrame(brands_data)
            st.dataframe(df, use_container_width=True)
            csv_string = df.to_csv(index=False, encoding='utf-8-sig') # UTF-8 with BOM for Excel compatibility
            st.download_button(
               label="CSV Olarak İndir",
               data=csv_string,
               file_name='sephora_markalar.csv',
               mime='text/csv',
            )

    except UnicodeDecodeError:
        st.error("Dosya kodlaması UTF-8 değil gibi görünüyor. Lütfen UTF-8 formatında kaydedilmiş bir HTML dosyası yükleyin.")
    except Exception as e:
        st.error(f"Dosya işlenirken bir hata oluştu: {e}")
