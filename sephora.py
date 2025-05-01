import streamlit as st
from bs4 import BeautifulSoup
import pandas as pd
import re
import json
from io import StringIO
import os

# Sayfa Başlığı
st.set_page_config(page_title="Sephora Marka Filtre Çekici", layout="wide")
st.title("💄 Sephora Marka Filtre Veri Çekici (HTML Yükleme)")
st.caption("Kaydettiğiniz Sephora ürün listeleme sayfası HTML dosyasını yükleyerek marka filtresindeki verileri CSV olarak indirin.")

# --- Kullanıcı Talimatları ---
st.info("""
**Nasıl Kullanılır:**
1.  Marka filtrelerini çekmek istediğiniz Sephora ürün listeleme sayfasını (örn: Makyaj, Parfüm kategorisi) **web tarayıcınızda** açın.
2.  Sayfanın **tamamen** yüklendiğinden emin olun (sol taraftaki **"Refine"** veya benzeri bölümdeki **"Brands"** filtresinin ve markaların görünür olduğundan emin olun).
3.  Tarayıcıda sayfaya sağ tıklayın ve **"Farklı Kaydet" (Save Page As...)** seçeneğini seçin.
4.  Kayıt türü olarak **"Web Sayfası, Sadece HTML" (Webpage, HTML Only)** veya **"Web Sayfası, Tamamı" (Webpage, Complete)** seçeneklerinden birini seçin. **"Sadece HTML" genellikle daha iyidir.** Dosya uzantısı `.html` veya `.htm` olmalıdır.
5.  Kaydettiğiniz bu `.html` dosyasını aşağıdaki "Gözat" düğmesini kullanarak yükleyin.
""")

# --- Fonksiyonlar ---

def find_nested_data(data, target_key, target_value):
    """
    İç içe geçmiş dictionary ve listelerde belirli bir anahtar-değer çiftini
    içeren dictionary'yi arar.
    """
    if isinstance(data, dict):
        if data.get(target_key) == target_value:
            return data
        for key, value in data.items():
            # Çok büyük veya alakasız dalları budama (opsiyonel, dikkatli kullanılmalı)
            # if key in ['big_list_key', 'unrelated_data']: continue
            found = find_nested_data(value, target_key, target_value)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = find_nested_data(item, target_key, target_value)
            if found:
                return found
    return None

def extract_brands_from_next_data(script_content):
    """__NEXT_DATA__ script içeriğinden marka verilerini çıkarır."""
    brands_data = []
    processed_brands = set()
    try:
        next_data = json.loads(script_content)
        st.success("__NEXT_DATA__ JSON olarak başarıyla parse edildi.")

        # 'attributeId': 'c_brand' içeren dictionary'yi bulmaya çalış
        # Daha derinlerde olabilir, genel arama yapalım
        brand_filter_dict = find_nested_data(next_data, 'attributeId', 'c_brand')

        if brand_filter_dict:
            st.success("'c_brand' attributeId içeren yapı bulundu.")
            if 'values' in brand_filter_dict and isinstance(brand_filter_dict['values'], list):
                st.info(f"Marka 'values' listesinde {len(brand_filter_dict['values'])} öğe bulundu.")
                for item in brand_filter_dict['values']:
                    if isinstance(item, dict) and 'label' in item and 'hitCount' in item:
                        brand_name = item['label'].strip()
                        hit_count = item['hitCount']
                        # Geçerli veri kontrolü
                        if brand_name and isinstance(hit_count, int) and brand_name.lower() != 'no' and brand_name not in processed_brands:
                            brands_data.append({'Marka': brand_name, 'Ürün Sayısı': hit_count})
                            processed_brands.add(brand_name)
                if brands_data:
                    st.info(f"{len(brands_data)} geçerli marka/sayı çifti ayıklandı.")
                    return pd.DataFrame(brands_data)
                else:
                    st.warning("Marka filtresi ('c_brand') bulundu ancak içinde geçerli 'label' ve 'hitCount' içeren öğe bulunamadı.")
                    return pd.DataFrame() # Boş DataFrame
            else:
                st.warning("'c_brand' yapısı bulundu ancak geçerli bir 'values' listesi içermiyor.")
                # st.json(brand_filter_dict) # Bulunan yapıyı göster (debug)
                return None
        else:
            st.warning("__NEXT_DATA__ içinde 'c_brand' attributeId'li filtre yapısı bulunamadı.")
            # Anahtar yapıları görmek için verinin bir kısmını yazdırabiliriz (debug)
            # if 'props' in next_data and 'pageProps' in next_data['props']:
            #     st.json(list(next_data['props']['pageProps'].keys()))
            return None

    except json.JSONDecodeError as e:
        st.error(f"__NEXT_DATA__ içeriği JSON olarak ayrıştırılamadı: {e}")
        st.text("HTML dosyasının 'Sadece HTML' olarak kaydedildiğinden emin olun.")
        return None
    except Exception as e:
        st.error(f"__NEXT_DATA__ işlenirken beklenmedik bir hata oluştu: {e}")
        return None


def extract_brands_directly(soup):
    """Alternatif yöntem: Doğrudan HTML elementlerini parse etmeye çalışır (Daha Basit)."""
    st.info("Alternatif yöntem (HTML elementleri) deneniyor...")
    brands_data = []
    processed_brands = set()

    # Filtre bölümünü bulmak için daha genel bir yaklaşım deneyelim
    # İçinde 'Refine', 'Filter', 'Brands' gibi kelimeler geçen ve liste içeren yapılar ara
    possible_sections = soup.find_all(['div', 'aside', 'section'], class_=re.compile(r'filter|facet|refine', re.IGNORECASE))
    if not possible_sections:
        # ID'leri deneyelim
         possible_sections = soup.find_all(id=re.compile(r'filter|facet', re.IGNORECASE))

    brand_section = None
    for section in possible_sections:
         # İçinde 'brand' kelimesi geçen bir input veya çok sayıda potansiyel filtre değeri var mı?
         # Veya doğrudan 'Brands' başlığını içeriyor mu?
         if section.find(['h3','h2','button'], string=re.compile(r'Brands?', re.IGNORECASE)) or \
            section.find('input', attrs={'name': re.compile(r'brand', re.IGNORECASE)}) or \
            len(section.find_all(['label', 'li', 'div'], class_=re.compile(r'checkbox|facet-value|option', re.IGNORECASE))) > 5:
                brand_section = section
                st.info(f"Potansiyel filtre bölümü bulundu: <{brand_section.name} class='{brand_section.get('class', 'N/A')}' id='{brand_section.get('id', 'N/A')}'>")
                break # İlk uygun olanı al

    if not brand_section:
        st.error("Marka filtresi bölümü HTML içinde otomatik olarak tespit edilemedi.")
        return None

    # Marka listesi öğelerini (genellikle label veya onu içeren div/li) bul
    # Class isimleri çok değişken olabilir, yapısal olarak arayalım
    # İçinde checkbox olan label'ları veya checkbox'ın parent'larını hedefleyebiliriz
    items = brand_section.find_all('label', class_=re.compile(r'checkbox|facet', re.IGNORECASE))
    if not items:
        inputs = brand_section.find_all('input', type='checkbox', attrs={'name': re.compile(r'brand', re.IGNORECASE)})
        items = [inp.find_parent(['label','div','li']) for inp in inputs if inp.find_parent(['label','div','li'])]

    if not items:
        # Daha genel bir arama: içinde sayı olan parantez içeren herhangi bir liste öğesi
        items = brand_section.find_all(['li','div'], text=re.compile(r'\(\d+\)\s*$'))


    if not items:
        st.error("Marka listesi elementleri bulunamadı.")
        return None

    st.info(f"Bulunan olası marka elementi sayısı: {len(items)}")

    for item in items:
        text_content = item.get_text(separator=' ', strip=True)
        # Regex: Marka Adı (Sayı) formatını ara (daha toleranslı)
        match = re.search(r'^(.*?)\s*\((\d+)\)$', text_content)
        if match:
            brand_name = match.group(1).strip()
            count = int(match.group(2))
            # Temel filtreleme
            if brand_name and brand_name.lower() not in ['no', 'yes'] and brand_name not in processed_brands:
                brands_data.append({'Marka': brand_name, 'Ürün Sayısı': count})
                processed_brands.add(brand_name)

    if brands_data:
        st.success(f"{len(brands_data)} marka verisi doğrudan HTML'den başarıyla çekildi.")
        return pd.DataFrame(brands_data)
    else:
        st.warning("Doğrudan HTML taramasında yapısal marka verisi bulunamadı veya ayıklanamadı.")
        return None


# --- Streamlit Arayüzü ---
uploaded_file = st.file_uploader(
    "Kaydedilmiş Sephora HTML Dosyasını Yükleyin (.html/.htm)",
    type=["html", "htm"],
    accept_multiple_files=False
)

if uploaded_file is not None:
    st.success(f"'{uploaded_file.name}' başarıyla yüklendi.")
    with st.spinner("HTML dosyası okunuyor ve markalar ayrıştırılıyor..."):
        df_brands = None # Başlangıçta DataFrame'i None yapalım
        html_content = None
        try:
            # Dosya içeriğini oku ve decode et
            html_content = uploaded_file.getvalue().decode("utf-8")
            st.info("HTML içeriği okundu.")
        except UnicodeDecodeError:
            st.error("Dosya UTF-8 formatında okunamadı. Lütfen dosyayı tarayıcıdan 'Farklı Kaydet -> Web Sayfası, Sadece HTML' seçeneği ile tekrar kaydedip deneyin.")
        except Exception as e:
             st.error(f"Dosya okunurken hata oluştu: {e}")

        if html_content:
            # Önce __NEXT_DATA__ dene
            df_brands = extract_brands_from_next_data(html_content)

            # __NEXT_DATA__ başarısız olursa veya boş dönerse alternatif yöntemi dene
            if df_brands is None or df_brands.empty:
                 st.info("__NEXT_DATA__ başarısız oldu veya veri bulunamadı, doğrudan HTML deneniyor.")
                 try:
                     soup_alt = BeautifulSoup(html_content, 'lxml')
                     df_brands = extract_brands_directly(soup_alt)
                 except Exception as e:
                     st.error(f"Alternatif HTML ayrıştırma yönteminde hata oluştu: {e}")
                     df_brands = None # Hata durumunda None yap

            # Sonucu göster ve CSV indir
            if df_brands is not None and not df_brands.empty:
                st.subheader("Çekilen Marka Verileri")
                st.dataframe(df_brands.set_index('Marka'), use_container_width=True)
                # --- CSV İndirme ---
                try:
                    csv_buffer = StringIO()
                    df_brands.to_csv(csv_buffer, index=False, encoding='utf-8')
                    csv_data = csv_buffer.getvalue()
                    base_filename = os.path.splitext(uploaded_file.name)[0]
                    csv_filename = f"sephora_markalar_{base_filename}.csv"
                    st.download_button(
                        label="💾 CSV Olarak İndir",
                        data=csv_data,
                        file_name=csv_filename,
                        mime='text/csv',
                    )
                except Exception as e:
                    st.error(f"CSV oluşturulurken/indirilirken hata: {e}")
            elif df_brands is not None: # Boş DataFrame geldiyse
                 st.warning("Yüklenen HTML dosyasında, her iki yöntemle de (__NEXT_DATA__ veya doğrudan HTML tarama) marka filtresi verisi bulunamadı veya ayıklanamadı.")
            # else: Hata zaten yukarıda gösterildi.


st.markdown("---")
st.caption("Not: Bu uygulama, yüklediğiniz HTML dosyasının içindeki verilere dayanır. En iyi sonuç için sayfayı tarayıcıda **tamamen yüklendikten sonra** 'Farklı Kaydet -> Web Sayfası, Sadece HTML' olarak kaydedin.")
