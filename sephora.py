import streamlit as st
from bs4 import BeautifulSoup
import pandas as pd
import re
import json
from io import StringIO
import os

# Sayfa Başlığı ve Talimatlar (Aynı)
st.set_page_config(page_title="Sephora Marka Filtre Çekici", layout="wide")
st.title("💄 Sephora Marka Filtre Veri Çekici (HTML Yükleme)2")
st.caption("Kaydettiğiniz Sephora ürün listeleme sayfası HTML dosyasını yükleyerek marka filtresindeki verileri CSV olarak indirin.")
st.info("""
**Nasıl Kullanılır:**
1.  Marka filtrelerini çekmek istediğiniz Sephora ürün listeleme sayfasını (örn: Makyaj, Parfüm kategorisi) **web tarayıcınızda** açın.
2.  Sayfanın **tamamen** yüklendiğinden emin olun (sol taraftaki **"Refine"** veya benzeri bölümdeki **"Brands"** filtresinin ve markaların görünür olduğundan emin olun).
3.  Tarayıcıda sayfaya sağ tıklayın ve **"Farklı Kaydet" (Save Page As...)** seçeneğini seçin.
4.  Kayıt türü olarak **"Web Sayfası, Sadece HTML" (Webpage, HTML Only)** seçeneğini seçin. Dosya uzantısı `.html` veya `.htm` olmalıdır.
5.  Kaydettiğiniz bu `.html` dosyasını aşağıdaki "Gözat" düğmesini kullanarak yükleyin.
""")

# --- Fonksiyonlar ---

def find_nested_data(data, target_key, target_value):
    """İç içe geçmiş dict/list'lerde belirli bir anahtar-değer çiftini arar."""
    if isinstance(data, dict):
        if data.get(target_key) == target_value:
            return data
        for key, value in data.items():
            # Basit performans iyileştirmesi: Çok büyük listeleri/sözlükleri atla
            if isinstance(value, (dict, list)) and len(str(value)) > 5000: # Boyut eşiği ayarlanabilir
                 continue
            found = find_nested_data(value, target_key, target_value)
            if found: return found
    elif isinstance(data, list):
        # Çok uzun listelerde aramayı sınırlama (opsiyonel)
        items_to_check = data #[:500] if len(data) > 500 else data
        for item in items_to_check:
            found = find_nested_data(item, target_key, target_value)
            if found: return found
    return None

def extract_brands_from_next_data(soup):
    """__NEXT_DATA__ script'inden marka verilerini çıkarır (Daha sağlam içerik alma)."""
    brands_data = []
    processed_brands = set()
    script_tag = soup.find('script', id='__NEXT_DATA__')

    if not script_tag:
        st.warning("__NEXT_DATA__ script etiketi HTML içinde bulunamadı.")
        return None

    st.info("__NEXT_DATA__ script etiketi bulundu.")

    # İçeriği almayı dene (önce .string, olmazsa .get_text())
    script_content = None
    if script_tag.string:
        script_content = script_tag.string.strip()
        st.info(".string ile içerik alındı.")
    else:
        st.warning(".string ile içerik alınamadı (None), .get_text() deneniyor...")
        script_content = script_tag.get_text(strip=True)
        if script_content:
             st.info(".get_text() ile içerik alındı.")
        else:
             st.error("__NEXT_DATA__ etiketi bulundu ancak ne .string ne de .get_text() ile içerik alınamadı.")
             return None


    if not script_content:
        st.error("__NEXT_DATA__ etiketi bulundu ancak içeriği boş.")
        return None

    st.info(f"__NEXT_DATA__ içeriğinin başı (ilk 500 karakter):\n```json\n{script_content[:500]}...\n```")

    # JSON ayrıştırmayı dene
    try:
        # Bazen başta/sonda gereksiz karakterler olabilir, JSON nesnesinin başladığı yerden almayı dene
        json_start_index = script_content.find('{')
        json_end_index = script_content.rfind('}') + 1
        if json_start_index != -1 and json_end_index != 0:
            potential_json = script_content[json_start_index:json_end_index]
            next_data = json.loads(potential_json)
            st.success("__NEXT_DATA__ içeriği JSON olarak başarıyla ayrıştırıldı.")
        else:
            st.error("__NEXT_DATA__ içeriğinde geçerli JSON başlangıcı/bitişi bulunamadı.")
            return None

        # 'attributeId': 'c_brand' içeren yapıyı bul
        brand_filter_dict = find_nested_data(next_data, 'attributeId', 'c_brand')

        if brand_filter_dict:
            st.success("'c_brand' attributeId içeren yapı bulundu.")
            if 'values' in brand_filter_dict and isinstance(brand_filter_dict['values'], list):
                st.info(f"Marka 'values' listesinde {len(brand_filter_dict['values'])} öğe bulundu.")
                for item in brand_filter_dict['values']:
                    if isinstance(item, dict) and 'label' in item and 'hitCount' in item:
                        brand_name = item['label'].strip()
                        hit_count = item['hitCount']
                        if brand_name and isinstance(hit_count, int) and brand_name.lower() != 'no' and brand_name not in processed_brands:
                            brands_data.append({'Marka': brand_name, 'Ürün Sayısı': hit_count})
                            processed_brands.add(brand_name)
                if brands_data:
                    st.info(f"{len(brands_data)} geçerli marka/sayı çifti __NEXT_DATA__ içinden ayıklandı.")
                    return pd.DataFrame(brands_data)
                else:
                    st.warning("Marka filtresi ('c_brand') bulundu ancak içinde geçerli öğe bulunamadı.")
                    return pd.DataFrame()
            else:
                st.warning("'c_brand' yapısı bulundu ancak geçerli 'values' listesi yok.")
                return None
        else:
            st.warning("__NEXT_DATA__ içinde 'c_brand' yapısı bulunamadı.")
            return None

    except json.JSONDecodeError as e:
        st.error(f"__NEXT_DATA__ içeriği JSON olarak ayrıştırılamadı: {e}")
        st.error("Hatanın oluştuğu yerdeki içerik (ilk 100 karakter): " + repr(script_content[:100]))
        return None
    except Exception as e:
        st.error(f"__NEXT_DATA__ işlenirken beklenmedik hata: {e}")
        return None


def extract_brands_directly(soup):
    """Alternatif yöntem: Doğrudan HTML elementlerini parse etmeye çalışır."""
    # Bu fonksiyon şimdilik aynı kalabilir, __NEXT_DATA__'nın çalışması öncelikli.
    st.info("Alternatif yöntem (doğrudan HTML elementleri) deneniyor...")
    # ... (önceki kodla aynı) ...
    brands_data = []
    processed_brands = set()
    try:
        brand_section = None
        css_selectors = [
            'div[data-testid="facet-container-Brands"]',
            'div[data-testid="Brands"]',
            'div[aria-labelledby*="brand"]',
            'section[aria-labelledby*="brand"]',
            'aside[aria-labelledby*="brand"]'
        ]
        for selector in css_selectors:
            found_section = soup.select_one(selector)
            if found_section:
                brand_section = found_section
                st.info(f"Potansiyel filtre bölümü CSS seçici ile bulundu: '{selector}'")
                break

        if not brand_section:
            st.warning("CSS seçicileri ile filtre bölümü bulunamadı, metin araması yapılıyor...")
            possible_headers = soup.find_all(['h3', 'h2', 'button', 'div'], string=re.compile(r'^\s*Brands?\s*$', re.IGNORECASE))
            for header in possible_headers:
                current = header
                for _ in range(5):
                    parent = current.find_parent(['div', 'section', 'aside'])
                    if parent and (parent.find('input', type='checkbox') or len(parent.find_all('li')) > 2):
                        brand_section = parent
                        st.info(f"'Brands' başlığından yola çıkarak parent bulundu: <{brand_section.name} class='{brand_section.get('class', 'N/A')}' id='{brand_section.get('id', 'N/A')}'>")
                        break
                    if not parent: break
                    current = parent
                if brand_section: break

        if not brand_section:
            st.error("Marka filtresi bölümü HTML içinde otomatik olarak tespit edilemedi (Alternatif Yöntem).")
            return None

        items = brand_section.find_all('label', class_=re.compile(r'checkbox|facet', re.IGNORECASE))
        if not items:
            inputs = brand_section.find_all('input', type='checkbox')
            items = [inp.find_parent(['label','div','li']) for inp in inputs if inp.find_parent(['label','div','li'])]
        if not items:
             items = brand_section.find_all(['li','div'], text=re.compile(r'\(\d+\)\s*$'))

        if not items:
            st.error("Marka listesi elementleri bulunamadı.")
            return None

        st.info(f"Bulunan olası marka elementi sayısı: {len(items)}")

        for item in items:
            text_content = item.get_text(separator=' ', strip=True)
            match = re.search(r'([a-zA-Z0-9 &\'\+\.-]+)\s*\((\d+)\)', text_content)
            if match:
                brand_name = match.group(1).strip()
                count = int(match.group(2))
                if brand_name and brand_name.lower() not in ['no', 'yes'] and brand_name not in processed_brands:
                    brands_data.append({'Marka': brand_name, 'Ürün Sayısı': count})
                    processed_brands.add(brand_name)

        if brands_data:
            st.success(f"{len(brands_data)} marka verisi doğrudan HTML'den başarıyla çekildi.")
            return pd.DataFrame(brands_data)
        else:
            st.warning("Doğrudan HTML taramasında yapısal marka verisi bulunamadı veya ayıklanamadı.")
            return None

    except Exception as e:
        st.error(f"Markaları doğrudan HTML'den çekerken hata oluştu (Alternatif Yöntem): {e}")
        return None


# --- Streamlit Arayüzü (Ana işleyiş aynı) ---
uploaded_file = st.file_uploader(
    "Kaydedilmiş Sephora HTML Dosyasını Yükleyin (.html/.htm)",
    type=["html", "htm"],
    accept_multiple_files=False
)

if uploaded_file is not None:
    st.success(f"'{uploaded_file.name}' başarıyla yüklendi.")
    with st.spinner("HTML dosyası okunuyor ve markalar ayrıştırılıyor..."):
        df_brands = None
        html_content = None
        try:
            html_content_bytes = uploaded_file.getvalue()
            try:
                html_content = html_content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                st.warning("UTF-8 ile decode edilemedi, latin-1 deneniyor...")
                html_content = html_content_bytes.decode("latin-1")
            st.info("HTML içeriği okundu.")
        except Exception as e:
             st.error(f"Dosya okunurken/decode edilirken hata oluştu: {e}")

        if html_content:
            try:
                 soup = BeautifulSoup(html_content, 'lxml')
                 st.info("HTML, BeautifulSoup ile başarıyla parse edildi.")

                 # Önce __NEXT_DATA__ dene
                 df_brands = extract_brands_from_next_data(soup) # Güncellenmiş fonksiyonu çağır

                 # Başarısız olursa veya boş dönerse alternatif yöntemi dene
                 if df_brands is None or df_brands.empty:
                      if df_brands is None:
                           st.info("__NEXT_DATA__ bulunamadı veya işlenemedi, doğrudan HTML deneniyor.")
                      else:
                           st.info("__NEXT_DATA__ işlendi ancak veri bulunamadı, doğrudan HTML deneniyor.")
                      try:
                          df_brands = extract_brands_directly(soup) # Alternatif yöntem
                      except Exception as e:
                          st.error(f"Alternatif HTML ayrıştırma yönteminde hata oluştu: {e}")
                          df_brands = None

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
                      st.warning("Yüklenen HTML dosyasında, denenen yöntemlerle marka filtresi verisi bulunamadı.")
                 # else: df_brands = None ise hata zaten yukarıda verildi.

            except Exception as e:
                st.error(f"HTML içeriği BeautifulSoup ile parse edilirken hata oluştu: {e}")

st.markdown("---")
st.caption("Not: Bu uygulama, yüklediğiniz HTML dosyasının içindeki verilere dayanır. En iyi sonuç için sayfayı tarayıcıda **tamamen yüklendikten sonra** 'Farklı Kaydet -> Web Sayfası, Sadece HTML' olarak kaydedin.")
