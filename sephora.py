import streamlit as st
import pandas as pd
import re
from bs4 import BeautifulSoup
import io

st.set_page_config(page_title="Sephora Marka Çıkarıcı", layout="wide")

st.title("💄 Sephora Marka Filtresi Veri Çıkarıcı")
st.write("Lütfen Sephora ürün listeleme sayfasının indirilmiş HTML dosyasını yükleyin.")
st.caption("Örnek dosya: 'Makeup Essentials_ Lips, Eyes & Skin ≡ Sephora.html'")

def extract_brands_from_html_elements(html_content):
    """
    Parses HTML content string to find brand filter elements directly within the HTML structure.
    Looks for checkboxes and associated labels containing brand names and counts.

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

    brands_data = []
    fieldnames = ['Marka', 'Urun Adedi']

    st.write("HTML elemanları içinde marka filtresi aranıyor...")

    # Potansiyel olarak filtreleri içeren bölümü bulmaya çalışalım.
    # Bu kısım sitenin yapısına göre değişebilir, daha genel seçiciler deneyelim.
    # Örnek: Filtre başlığının 'Brands' olduğu bir bölüm arayabiliriz.
    brands_section = None
    possible_headers = soup.find_all(['h2', 'h3', 'h4', 'button', 'div'], string=re.compile(r'^\s*Brands\s*$', re.IGNORECASE))

    if not possible_headers:
        st.warning("HTML içinde 'Brands' başlığına sahip belirgin bir bölüm bulunamadı. Checkbox'lar aranacak.")
        # Alternatif: Doğrudan checkbox'ları arayalım
        filter_elements = soup.find_all('div', {'data-testid': re.compile(r'facet-filter-container', re.IGNORECASE)}) # TestID'den yola çıkalım
        if not filter_elements:
            filter_elements = soup.find_all('input', {'type':'checkbox'}) # En genel arama
            st.info(f"TestID bulunamadı, {len(filter_elements)} adet checkbox bulundu.")
    else:
        # Başlık bulunduysa, onun ebeveynini veya yakınındaki liste elemanını bulmaya çalışalım
        st.info(f"'Brands' başlığı içeren {len(possible_headers)} element bulundu. İlk bulunanın etrafı taranacak.")
        # Genellikle filtreler başlığın kardeş veya ebeveyninin içindedir.
        # Bu kısım daha karmaşık hale gelebilir ve sitenin yapısına bağlıdır.
        # Şimdilik basitçe tüm checkbox'ları aramaya devam edelim, ancak başlığın bulunması iyiye işaret.
        filter_elements = soup.find_all('input', {'type':'checkbox'}) # Yine de tüm checkbox'ları arayalım

    # Marka adını ve sayısını içeren kalıbı bulmak için regex
    # Örnek: "BRAND NAME (123)"
    brand_pattern = re.compile(r'^(.*?)\s*\((\d+)\)\s*$')

    processed_labels = set() # Aynı label'ı tekrar işlememek için

    for element in filter_elements:
        # Checkbox'ın ilişkili label'ını bulmaya çalışalım
        label_element = None
        # 1. 'id' varsa ve 'for' ile eşleşen label varsa
        if element.has_attr('id'):
            label_element = soup.find('label', {'for': element['id']})

        # 2. Label checkbox'ı kapsıyorsa (ebeveyn ise)
        if not label_element and element.parent and element.parent.name == 'label':
            label_element = element.parent

        # 3. Checkbox ile aynı seviyede veya yakınında bir label/span varsa (daha az güvenilir)
        if not label_element:
             sibling_label = element.find_next_sibling(['label', 'span'])
             if sibling_label:
                 label_element = sibling_label
             else:
                 parent_label = element.find_parent(['label', 'div']) # Yakındaki bir div'i de kontrol et
                 if parent_label:
                     # İçinde sadece bu checkbox ve metin olup olmadığını kontrol et
                     if parent_label.find('input', {'type':'checkbox'}) == element:
                          label_element = parent_label


        if label_element:
            label_text = label_element.get_text(strip=True)

            # Eğer bu label daha önce işlendiyse atla
            if label_text in processed_labels:
                continue
            processed_labels.add(label_text)

            match = brand_pattern.match(label_text)
            if match:
                brand_name = match.group(1).strip()
                hit_count = int(match.group(2))
                # Marka adının mantıklı görünüp görünmediğini kontrol et (örn. tek harf olmamalı)
                if len(brand_name) > 1:
                    brands_data.append({
                        fieldnames[0]: brand_name,
                        fieldnames[1]: hit_count
                    })
                    # st.write(f"Bulundu: {brand_name} ({hit_count})") # Debug

    if not brands_data:
        st.error("HTML elemanları (checkbox/label) içinde marka ve ürün sayısı bilgisi bulunamadı. Sayfa yapısı beklenenden farklı olabilir veya veri script içinde farklı bir formatta bulunuyor olabilir.")
        return None, None

    st.info(f"Toplam {len(brands_data)} marka bulundu.")
    return brands_data, fieldnames

# --- Streamlit File Uploader ---
uploaded_file = st.file_uploader("HTML Dosyasını Buraya Sürükleyin veya Seçin", type=["html", "htm"])

if uploaded_file is not None:
    try:
        stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
        html_content = stringio.read()
        st.success(f"'{uploaded_file.name}' başarıyla yüklendi ve okundu.")

        with st.spinner("Marka verileri çıkarılıyor..."):
            # Yeni fonksiyonu çağır
            brands_data, headers = extract_brands_from_html_elements(html_content)

        if brands_data and headers:
            st.success("Marka verileri başarıyla çıkarıldı!")
            df = pd.DataFrame(brands_data)
            # Markaya göre sırala
            df = df.sort_values(by='Marka').reset_index(drop=True)
            st.dataframe(df, use_container_width=True)
            csv_string = df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
               label="CSV Olarak İndir",
               data=csv_string,
               file_name='sephora_markalar.csv',
               mime='text/csv',
            )
        # else: # Hata mesajı fonksiyon içinde veriliyor

    except UnicodeDecodeError:
        st.error("Dosya kodlaması UTF-8 değil gibi görünüyor. Lütfen UTF-8 formatında kaydedilmiş bir HTML dosyası yükleyin.")
    except Exception as e:
        st.error(f"Dosya işlenirken genel bir hata oluştu: {e}")
        st.exception(e)
