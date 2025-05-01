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
    extracts brand names and their hit counts. Applies regex directly without pre-check.

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
    found_potential_match_script = False # Eşleşme denemesi yapılan script bulundu mu?
    fieldnames = ['Marka', 'Urun Adedi']

    # Regex: "attributeId":"c_brand" ve ardından gelen ilk "values": [...] yapısını arar.
    pattern = re.compile(r'"attributeId"\s*:\s*"c_brand".*?"values"\s*:\s*(\[.*?\])', re.DOTALL)

    st.write(f"Toplam {len(scripts)} script etiketi bulundu ve kontrol ediliyor...")
    matched_scripts_content = [] # Regex'in eşleştiği script içeriklerini sakla

    for i, script in enumerate(scripts):
        script_content = script.get_text()
        if script_content:
            match = pattern.search(script_content)
            if match:
                found_potential_match_script = True # Regex en az bir script'te eşleşti
                st.info(f"Script #{i+1} içinde regex deseni eşleşti.")
                matched_scripts_content.append(f"--- Script #{i+1} (Regex Eşleşti) ---\n{script_content[:1500]}...\n----------------------------------------\n")

                json_like_string = match.group(1)
                json_like_string = json_like_string.strip()
                if json_like_string.endswith(','):
                   json_like_string = json_like_string[:-1]

                try:
                    data_list = json.loads(json_like_string)

                    if isinstance(data_list, list) and data_list:
                        processed_count_in_script = 0
                        for item in data_list:
                            if (isinstance(item, dict) and
                                    'label' in item and isinstance(item['label'], str) and
                                    'hitCount' in item and isinstance(item['hitCount'], int)):
                                # Markayı ve sayısını eklemeden önce zaten listede olup olmadığını kontrol et
                                current_brand_label = item['label']
                                if not any(d['Marka'] == current_brand_label for d in brands_data):
                                    brands_data.append({
                                        fieldnames[0]: current_brand_label,
                                        fieldnames[1]: item['hitCount']
                                    })
                                    processed_count_in_script += 1
                                # else: # Zaten eklenmişse tekrar ekleme
                                #     st.write(f"Marka '{current_brand_label}' zaten eklenmiş, atlanıyor.")

                        if processed_count_in_script > 0:
                           st.success(f"Script #{i+1}: {processed_count_in_script} adet geçerli ve yeni marka/ürün sayısı bulundu ve eklendi.")
                           found_data = True # En az bir geçerli veri bulundu
                           # break # Genellikle tek yerde olduğu için burada durulabilir, ama emin olmak için devam edelim.
                        # else:
                           # st.warning(f"Script #{i+1}: JSON listesi ayrıştırıldı ancak içinde geçerli marka öğesi bulunamadı.")
                    # else:
                         # st.warning(f"Script #{i+1}: Regex eşleşti ancak ayrıştırılan veri beklenen liste formatında değil veya boş.")

                except json.JSONDecodeError as e:
                    st.warning(f"Script #{i+1} içinde JSON ayrıştırma hatası: {e}. Yakalanan veri: {json_like_string[:200]}...")
                except Exception as e:
                    st.error(f"Script #{i+1} işlenirken beklenmedik bir hata: {e}")

    if not found_data: # Eğer döngü bittiğinde hiç geçerli veri eklenmemişse
        st.error("HTML içinde geçerli marka filtresi verisi bulunamadı.")
        if found_potential_match_script:
             st.warning("Ancak, regex deseniyle eşleşen script(ler) bulundu. Muhtemelen JSON yapısı veya içeriği beklenenden farklı. Lütfen aşağıdaki script içeriklerini inceleyin:")
             with st.expander("Regex ile Eşleşen Script İçerikleri (İlk 1500 Karakter)"):
                 for content in matched_scripts_content:
                     st.code(content, language='javascript')
        else:
             st.warning("Regex deseniyle eşleşen hiçbir script etiketi bulunamadı. HTML kaynağını veya regex desenini kontrol edin.")
        return None, None

    st.info(f"Toplam {len(brands_data)} marka bulundu ve işlendi.")
    return brands_data, fieldnames

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
            # Markaya göre sıralama (isteğe bağlı)
            df = df.sort_values(by='Marka').reset_index(drop=True)
            st.dataframe(df, use_container_width=True)
            csv_string = df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
               label="CSV Olarak İndir",
               data=csv_string,
               file_name='sephora_markalar.csv',
               mime='text/csv',
            )
        # else: # Hata mesajı zaten fonksiyon içinde veriliyor

    except UnicodeDecodeError:
        st.error("Dosya kodlaması UTF-8 değil gibi görünüyor. Lütfen UTF-8 formatında kaydedilmiş bir HTML dosyası yükleyin.")
    except Exception as e:
        st.error(f"Dosya işlenirken genel bir hata oluştu: {e}")
        st.exception(e)
