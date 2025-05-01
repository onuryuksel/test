import streamlit as st
from bs4 import BeautifulSoup
import pandas as pd
import re
import json
from io import StringIO
import os

# ... (Sayfa Başlığı, Talimatlar vb. aynı kalabilir) ...
st.set_page_config(page_title="Sephora Marka Filtre Çekici", layout="wide")
st.title("💄 Sephora Marka Filtre Veri Çekici (HTML Yükleme)")
st.caption("Kaydettiğiniz Sephora ürün listeleme sayfası HTML dosyasını yükleyerek marka filtresindeki verileri CSV olarak indirin.")
st.info("""
**Nasıl Kullanılır:**
1.  Marka filtrelerini çekmek istediğiniz Sephora ürün listeleme sayfasını (örn: Makyaj, Parfüm kategorisi) **web tarayıcınızda** açın.
2.  Sayfanın **tamamen** yüklendiğinden emin olun (sol taraftaki **"Refine"** veya benzeri bölümdeki **"Brands"** filtresinin ve markaların görünür olduğundan emin olun).
3.  Tarayıcıda sayfaya sağ tıklayın ve **"Farklı Kaydet" (Save Page As...)** seçeneğini seçin.
4.  Kayıt türü olarak **"Web Sayfası, Sadece HTML" (Webpage, HTML Only)** seçeneğini seçin. Dosya uzantısı `.html` veya `.htm` olmalıdır.
5.  Kaydettiğiniz bu `.html` dosyasını aşağıdaki "Gözat" düğmesini kullanarak yükleyin.
""")

def find_nested_data(data, target_key, target_value):
    """İç içe geçmiş dict/list'lerde belirli bir anahtar-değer çiftini arar."""
    if isinstance(data, dict):
        if data.get(target_key) == target_value:
            return data
        for key, value in data.items():
            found = find_nested_data(value, target_key, target_value)
            if found: return found
    elif isinstance(data, list):
        for item in data:
            found = find_nested_data(item, target_key, target_value)
            if found: return found
    return None

def extract_brands_from_potential_next_data(soup):
    """ID'siz olarak __NEXT_DATA__ benzeri script'leri bulup işlemeyi dener."""
    st.info("__NEXT_DATA__ ID'li script bulunamadı, potansiyel veri scriptleri aranıyor...")
    scripts = soup.find_all('script')
    st.info(f"Toplam {len(scripts)} script etiketi bulundu.")
    potential_data_script = None

    for script in scripts:
        # İçeriği al ve kontrol et (boş etiketleri atla)
        script_content = script.string
        if script_content:
            script_content = script_content.strip()
            # İçeriğin JSON'a benzeyip benzemediğini kontrol et (basit kontrol)
            if script_content.startswith('{') and script_content.endswith('}') and 'props' in script_content[:500] and 'pageProps' in script_content[:1000]:
                 st.info("JSON'a benzeyen ve 'props', 'pageProps' içeren bir script bulundu.")
                 potential_data_script = script_content
                 break # İlk uygun olanı al

    if not potential_data_script:
        st.warning("JSON içeren potansiyel __NEXT_DATA__ script'i bulunamadı.")
        return None

    # JSON ayrıştırma ve veri çıkarma (öncekiyle aynı mantık)
    brands_data = []
    processed_brands = set()
    try:
        next_data = json.loads(potential_data_script)
        st.success("Potansiyel veri scripti JSON olarak başarıyla ayrıştırıldı.")
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
                    st.info(f"{len(brands_data)} geçerli marka/sayı çifti potansiyel __NEXT_DATA__ içinden ayıklandı.")
                    return pd.DataFrame(brands_data)
                else:
                    st.warning("Marka filtresi ('c_brand') bulundu ancak geçerli öğe yoktu.")
                    return pd.DataFrame()
            else:
                st.warning("'c_brand' yapısı bulundu ancak 'values' listesi yok.")
                return None
        else:
            st.warning("Potansiyel veri scripti içinde 'c_brand' yapısı bulunamadı.")
            return None
    except Exception as e:
        st.error(f"Potansiyel __NEXT_DATA__ işlenirken hata: {e}")
        return None

def extract_brands_directly_very_generic(soup):
    """ÇOK GENEL Alternatif yöntem: Sayfadaki tüm label'ları tarar."""
    st.info("En genel alternatif yöntem deneniyor (tüm label'lar taranıyor)...")
    brands_data = []
    processed_brands = set()

    # Sayfadaki TÜM label elementlerini bul
    all_labels = soup.find_all('label')
    st.info(f"Toplam {len(all_labels)} label etiketi bulundu.")

    if not all_labels:
        st.error("HTML içinde hiç label etiketi bulunamadı.")
        return None

    found_count = 0
    for label in all_labels:
        # Label'ın içinde checkbox var mı diye kontrol et (daha olası)
        checkbox = label.find('input', type='checkbox')
        # Checkbox yoksa bile metni kontrol et
        text_content = label.get_text(separator=' ', strip=True)
        # Regex: Marka Adı (Sayı) formatını ara
        match = re.search(r'([a-zA-Z0-9 &\'\+\.-]+)\s*\((\d+)\)$', text_content)
        if match:
            brand_name = match.group(1).strip()
            count = int(match.group(2))
            # Eğer checkbox varsa veya marka adı makul görünüyorsa ekle
            if checkbox or len(brand_name) > 1 : # Sadece checkbox olanları veya 1 karakterden uzun markaları al
                 if brand_name and brand_name.lower() not in ['no', 'yes'] and brand_name not in processed_brands:
                     brands_data.append({'Marka': brand_name, 'Ürün Sayısı': count})
                     processed_brands.add(brand_name)
                     found_count += 1

    if brands_data:
        st.success(f"{len(brands_data)} olası marka verisi HTML'deki label'lardan ayıklandı.")
        return pd.DataFrame(brands_data)
    else:
        st.warning("Genel HTML taramasında (label'lar) yapısal marka verisi bulunamadı.")
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
                 st.info("HTML, BeautifulSoup ile parse edildi.")

                 # Önce potansiyel __NEXT_DATA__ script'lerini dene
                 df_brands = extract_brands_from_potential_next_data(soup)

                 # O başarısız olursa veya boş dönerse en genel HTML tarama yöntemini dene
                 if df_brands is None or df_brands.empty:
                      if df_brands is None:
                           st.info("__NEXT_DATA__ benzeri script bulunamadı/işlenemedi, en genel HTML tarama deneniyor.")
                      else:
                           st.info("__NEXT_DATA__ benzeri script işlendi ancak veri bulunamadı, en genel HTML tarama deneniyor.")
                      try:
                          df_brands = extract_brands_directly_very_generic(soup)
                      except Exception as e:
                          st.error(f"En genel HTML ayrıştırma yönteminde hata oluştu: {e}")
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
                 # else: df_brands = None ise hata zaten yukarıda gösterildi.

            except Exception as e:
                st.error(f"HTML içeriği BeautifulSoup ile parse edilirken hata oluştu: {e}")

st.markdown("---")
st.caption("Not: Başarısız olursa, HTML dosyasını tarayıcıda açıp 'Brands' filtresinin olduğu bölümün HTML kodunu inceleyerek manuel kontrol edebilirsiniz.")
