import streamlit as st
# requests kütüphanesine artık gerek yok
from bs4 import BeautifulSoup
import pandas as pd
import re
import json
from io import StringIO
import os # Dosya adı işlemleri için

# Sayfa Başlığı
st.set_page_config(page_title="Sephora Marka Filtre Çekici", layout="wide")
st.title("💄 Sephora Marka Filtre Veri Çekici (HTML Yükleme)")
st.caption("Kaydettiğiniz Sephora ürün listeleme sayfası HTML dosyasını yükleyerek marka filtresindeki verileri CSV olarak indirin.")

# --- Kullanıcı Talimatları ---
st.info("""
**Nasıl Kullanılır:**
1.  Marka filtrelerini çekmek istediğiniz Sephora ürün listeleme sayfasını (örn: Makyaj, Parfüm kategorisi) **web tarayıcınızda** açın.
2.  Sayfanın **tamamen** yüklendiğinden emin olun (tüm ürünler ve filtreler görünür olmalı).
3.  Tarayıcıda sayfaya sağ tıklayın ve **"Farklı Kaydet" (Save Page As...)** seçeneğini seçin.
4.  Kayıt türü olarak **"Web Sayfası, Sadece HTML" (Webpage, HTML Only)** veya benzeri bir seçeneği seçin (Tüm sayfayı değil, sadece HTML'i kaydettiğinizden emin olun). Dosya uzantısı `.html` veya `.htm` olmalıdır.
5.  Kaydettiğiniz bu `.html` dosyasını aşağıdaki "Gözat" düğmesini kullanarak yükleyin.
""")

# --- Fonksiyonlar (Öncekiyle Büyük Ölçüde Aynı, fetch_* fonksiyonları kaldırıldı) ---

def find_brand_filter(data):
    """Recursive olarak JSON/dictionary içinde 'attributeId': 'c_brand' arar."""
    if isinstance(data, dict):
        if data.get('attributeId') == 'c_brand' and 'values' in data:
            if data.get('values') and isinstance(data['values'], list) and all(isinstance(item, dict) for item in data['values']):
                 return data
        # 'image' gibi büyük/gereksiz alanları atla (performans)
        for key, value in data.items():
            if key not in ['image', 'images', 'icon', 'icons', 'banner', 'banners', 'variations', 'attributes', 'promotions']:
                result = find_brand_filter(value)
                if result:
                    return result
    elif isinstance(data, list):
        # Çok uzun listelerde aramayı sınırlayabiliriz (opsiyonel)
        # items_to_check = data[:1000] if len(data) > 1000 else data
        items_to_check = data
        for item in items_to_check:
            result = find_brand_filter(item)
            if result:
                return result
    return None

def extract_brands_directly(soup):
    """Alternatif yöntem: Doğrudan HTML elementlerini parse etmeye çalışır."""
    st.info("Alternatif yöntem (HTML elementleri) deneniyor...")
    brands_data = []
    extracted_brands = set()
    try:
        # 'Brands' başlığını veya filtre bölümünü bul
        # Daha genel class isimleri veya yapısal ipuçları ara
        brand_section = None
        possible_headers = soup.find_all(['h3', 'h2', 'button', 'div'], string=re.compile(r'Brands?', re.IGNORECASE))
        for header in possible_headers:
            # Başlığın parent'larını kontrol et, filtre elemanları içeriyor mu?
            current = header
            for _ in range(5): # 5 seviye yukarı bak
                parent = current.find_parent(['div', 'section', 'aside'], class_=re.compile(r'filter|facet|refine', re.IGNORECASE))
                if parent and parent.find(['input', 'label'], class_=re.compile(r'checkbox|facet-value', re.IGNORECASE)):
                     brand_section = parent
                     st.info(f"Başlıktan potansiyel filtre bölümü bulundu: <{brand_section.name} class='{brand_section.get('class', [])}'>")
                     break
                if not parent: break
                current = parent
            if brand_section: break # İlk bulduğumuzla devam et

        if not brand_section:
            st.warning("Marka başlığından filtre bölümü bulunamadı. Genel container araması yapılıyor...")
            possible_sections = soup.find_all('div', class_=re.compile(r'filter|facet|refine', re.IGNORECASE))
            for section in possible_sections:
                 # İçinde 'brand' kelimesi geçen input veya çok sayıda potansiyel filtre değeri var mı?
                 if section.find('input', attrs={'name': re.compile(r'brand', re.IGNORECASE)}) or \
                    len(section.find_all(['label', 'li', 'div'], class_=re.compile(r'checkbox|facet-value|option', re.IGNORECASE))) > 3:
                    brand_section = section
                    st.info(f"Genel aramada potansiyel filtre bölümü bulundu: <{brand_section.name} class='{brand_section.get('class', [])}'>")
                    break

        if not brand_section:
            st.error("Marka filtresi bölümü HTML içinde bulunamadı (Alternatif Yöntem).")
            return None

        # Marka item'larını veya label'larını bul (daha geniş class araması)
        brand_items = brand_section.find_all(['div', 'li', 'label'], class_=re.compile(r'checkbox|facet-value|filter-value|facet-label|option', re.IGNORECASE))

        if not brand_items:
             # Sadece input'ları bulup parent'larından text almayı dene
             inputs = brand_section.find_all('input', type='checkbox', attrs={'name': re.compile(r'brand', re.IGNORECASE)})
             brand_items = [inp.find_parent('label') or inp.find_parent('div') for inp in inputs] # Parent label veya div ara
             brand_items = [item for item in brand_items if item] # None olanları kaldır

        if not brand_items:
            st.error("Marka listesi elementleri (item/label/input parent) bulunamadı.")
            return None

        st.info(f"Bulunan olası marka elementi sayısı: {len(brand_items)}")

        for item in brand_items:
            text_content = item.get_text(separator=' ', strip=True)
            # Regex: Başında potansiyel ikon/boşluk olabilecek Marka Adı (Sayı) veya Marka Adı Sayı
            match = re.search(r'^(?:[\W\s]*)?([a-zA-Z0-9 &\'\+.-]+?)\s*\(?(\d+)\)?$', text_content)
            if match:
                brand_name = match.group(1).strip()
                count = int(match.group(2))
                if brand_name.lower() not in ['no', 'yes', ''] and brand_name not in extracted_brands:
                    brands_data.append({'Marka': brand_name,'Ürün Sayısı': count})
                    extracted_brands.add(brand_name)

        if brands_data:
            st.success(f"{len(brands_data)} marka verisi doğrudan HTML'den başarıyla çekildi (Alternatif Yöntem).")
            return pd.DataFrame(brands_data)
        else:
            st.warning("Doğrudan HTML taramasında yapısal marka verisi bulunamadı veya ayıklanamadı.")
            return None

    except Exception as e:
        st.error(f"Markaları doğrudan HTML'den çekerken hata oluştu (Alternatif Yöntem): {e}")
        return None


def extract_brands_from_html(html_content):
    """HTML içeriğinden marka verilerini çıkarır (__NEXT_DATA__ öncelikli)."""
    if not html_content:
        st.error("HTML içeriği boş veya okunamadı.")
        return None

    soup = BeautifulSoup(html_content, 'lxml')
    brands_data = []
    processed_brands = set() # Yinelenenleri önlemek için

    # 1. __NEXT_DATA__ script'ini bul ve işle
    script_tag = soup.find('script', id='__NEXT_DATA__')
    if script_tag:
        st.info("__NEXT_DATA__ script'i bulundu, JSON verisi işleniyor...")
        try:
            next_data = json.loads(script_tag.string)
            brand_filter = find_brand_filter(next_data) # Recursive arama

            if brand_filter and 'values' in brand_filter and isinstance(brand_filter['values'], list):
                for item in brand_filter['values']:
                    if isinstance(item, dict) and 'label' in item and 'hitCount' in item:
                         brand_name = item['label'].strip()
                         # 'No' ve boş etiketleri ve tekrarları atla
                         if brand_name and brand_name.lower() != 'no' and brand_name not in processed_brands:
                            brands_data.append({
                                'Marka': brand_name,
                                'Ürün Sayısı': item.get('hitCount', 0) # hitCount yoksa 0
                            })
                            processed_brands.add(brand_name)

                if brands_data:
                     st.success(f"{len(brands_data)} marka verisi __NEXT_DATA__ içinden başarıyla çekildi.")
                     return pd.DataFrame(brands_data)
                else:
                     st.warning("__NEXT_DATA__ içinde marka filtresi ('c_brand') bulundu ancak geçerli marka/sayı çifti yoktu. Alternatif yöntem deneniyor...")
            else:
                st.warning("__NEXT_DATA__ içinde 'c_brand' filtresi bulunamadı. Alternatif yöntem deneniyor...")
        except Exception as e:
            st.error(f"__NEXT_DATA__ işlenirken hata: {e}. Alternatif yöntem deneniyor...")
    else:
        st.warning("__NEXT_DATA__ script'i bulunamadı. Alternatif yöntem (doğrudan HTML tarama) deneniyor...")

    # 2. Alternatif Yöntem: Doğrudan HTML'den çekmeyi dene
    return extract_brands_directly(soup)


# --- Streamlit Arayüzü ---
uploaded_file = st.file_uploader(
    "Kaydedilmiş Sephora HTML Dosyasını Yükleyin (.html/.htm)",
    type=["html", "htm"],
    accept_multiple_files=False
)

if uploaded_file is not None:
    st.success(f"'{uploaded_file.name}' başarıyla yüklendi.")
    with st.spinner("HTML dosyası okunuyor ve markalar ayrıştırılıyor..."):
        try:
            # Dosya içeriğini oku ve decode et
            html_content = uploaded_file.getvalue().decode("utf-8")
            st.info("HTML içeriği okundu.")

            # Markaları çıkar
            df_brands = extract_brands_from_html(html_content)

            if df_brands is not None and not df_brands.empty:
                st.subheader("Çekilen Marka Verileri")
                # DataFrame'i gösterirken indeksi gizle
                st.dataframe(df_brands.set_index('Marka'), use_container_width=True)

                # --- CSV İndirme ---
                try:
                    csv_buffer = StringIO()
                    df_brands.to_csv(csv_buffer, index=False, encoding='utf-8') # UTF-8 iyidir
                    csv_data = csv_buffer.getvalue()

                    # Yüklenen dosya adından CSV adı türet
                    base_filename = os.path.splitext(uploaded_file.name)[0]
                    csv_filename = f"sephora_markalar_{base_filename}.csv"

                    st.download_button(
                        label="💾 CSV Olarak İndir",
                        data=csv_data,
                        file_name=csv_filename,
                        mime='text/csv',
                    )
                except Exception as e:
                    st.error(f"CSV oluşturulurken veya indirme butonu hazırlanırken hata: {e}")

            elif df_brands is not None: # Boş DataFrame döndü
                 st.warning("Yüklenen HTML dosyasında marka filtresi verisi bulunamadı veya ayıklanamadı. Lütfen HTML'i 'Sadece HTML' olarak doğru kaydettiğinizden ve sayfanın tam yüklendiğinden emin olun.")
            # else: extract_brands_from_html içinde zaten hata mesajı verildi.

        except UnicodeDecodeError:
            st.error("Dosya UTF-8 formatında okunamadı. Lütfen dosyayı tarayıcıdan 'Farklı Kaydet -> Web Sayfası, Sadece HTML' seçeneği ile tekrar kaydedip deneyin.")
        except Exception as e:
            st.error(f"Dosya işlenirken beklenmedik bir hata oluştu: {e}")

st.markdown("---")
st.caption("Not: Bu uygulama, yüklediğiniz HTML dosyasının içindeki verilere dayanır. En iyi sonuç için sayfayı tarayıcıda 'Farklı Kaydet -> Web Sayfası, Sadece HTML' olarak kaydedin.")
