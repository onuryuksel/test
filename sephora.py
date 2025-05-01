import streamlit as st
import requests # Hata yakalama vb. için kalabilir
import cloudscraper # Eklendi
from bs4 import BeautifulSoup
import pandas as pd
import re
import json
from io import StringIO
import time

# Sayfa Başlığı
st.set_page_config(page_title="Sephora Marka Filtre Çekici", layout="wide")
st.title("💄 Sephora Marka Filtre Veri Çekici")
st.caption("Sephora ürün listeleme sayfası linkini girerek marka filtresindeki verileri CSV olarak indirin.")

# --- Fonksiyonlar ---

@st.cache_resource
def get_scraper():
    """Cloudscraper örneği oluşturur."""
    scraper = cloudscraper.create_scraper(
        browser={ # Tarayıcı gibi görünmek için ayarlar
            'browser': 'chrome',
            'platform': 'windows',
            'mobile': False,
            'desktop': True,
        },
         delay=10 # Cloudflare kontrolleri için gecikme (isteğe bağlı)
    )
    # Gerekirse ek header'lar eklenebilir, cloudscraper zaten yönetir ama deneyebiliriz.
    scraper.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9,tr-TR;q=0.8,tr;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    })
    return scraper

def fetch_html_cloudscraper(url):
    """Verilen URL'den HTML içeriğini cloudscraper ile çeker."""
    scraper = get_scraper()
    timeout_seconds = 60 # Timeout süresini yüksek tutalım
    try:
        st.info(f"URL alınıyor (cloudscraper, Timeout={timeout_seconds}s)... Lütfen bekleyin.")
        response = scraper.get(url, timeout=timeout_seconds)
        response.raise_for_status()

        if not response.content:
             st.warning(f"URL'den boş içerik alındı: {url}.")
             return None

        # Cloudscraper genellikle decode işlemini yapar ama kontrol edelim
        html_content = response.text
        st.success(f"URL başarıyla alındı (cloudscraper): {url}")
        return html_content

    except requests.exceptions.Timeout: # cloudscraper da requests tabanlı
        st.error(f"İstek zaman aşımına uğradı (Timeout={timeout_seconds}s): {url}")
        st.info("Sunucu yanıt vermedi. Sunucu yoğun olabilir veya cloudscraper engeli aşamadı.")
        return None
    except requests.exceptions.HTTPError as e:
         st.error(f"HTTP Hatası: {e.response.status_code} {e.response.reason} - URL: {url}")
         if e.response.status_code == 403:
              st.warning("403 Forbidden hatası alındı. Cloudflare/WAF koruması aktif olabilir ve aşılamamış olabilir.")
         elif e.response.status_code >= 500:
              st.warning("Sunucu hatası alındı.")
         return None
    except requests.exceptions.ConnectionError as e:
        st.error(f"Bağlantı Hatası: {e}")
        st.info("Bağlantı kurulamadı veya sunucu bağlantıyı kapattı. URL'yi kontrol edin veya ağ sorunlarını/engellemeleri değerlendirin.")
        return None
    except Exception as e: # cloudscraper'ın kendi hataları olabilir
        st.error(f"Cloudscraper ile URL alınırken hata oluştu: {e}")
        return None


# --- Marka Çıkarma Fonksiyonları (Önceki kodla aynı) ---

def find_brand_filter(data):
    """Recursive olarak JSON/dictionary içinde 'attributeId': 'c_brand' arar."""
    if isinstance(data, dict):
        if data.get('attributeId') == 'c_brand' and 'values' in data:
            if data['values'] and isinstance(data['values'], list) and all(isinstance(item, dict) for item in data['values']):
                 return data
        for key, value in data.items():
            if key not in ['image', 'images', 'icon', 'icons', 'banner', 'banners', 'variations', 'attributes']:
                result = find_brand_filter(value)
                if result:
                    return result
    elif isinstance(data, list):
        items_to_check = data
        for item in items_to_check:
            result = find_brand_filter(item)
            if result:
                return result
    return None

def extract_brands_directly(soup):
    """Alternatif yöntem: Doğrudan HTML elementlerini parse etmeye çalışır."""
    st.info("Alternatif yöntem: HTML elementleri taranıyor...")
    # ... (Bu fonksiyon öncekiyle aynı, detaylı arama yapıyor) ...
    brands_data = []
    try:
        brand_header = soup.find(['h3', 'h2', 'div', 'button'], string=re.compile(r'Brands?', re.IGNORECASE))
        brand_section = None
        if brand_header:
            current = brand_header
            for _ in range(5):
                 parent = current.find_parent(['div', 'section', 'aside'])
                 if parent and parent.find(['input', 'label'], class_=re.compile(r'checkbox|facet', re.IGNORECASE)):
                      brand_section = parent
                      st.info(f"Başlıktan parent bulundu: <{brand_section.name} class='{brand_section.get('class', 'N/A')}'>")
                      break
                 if not parent: break
                 current = parent
        if not brand_section:
            st.warning("Marka başlığından filtre bölümü bulunamadı. Genel arama...")
            possible_sections = soup.find_all('div', class_=re.compile(r'filter|facet|refine', re.IGNORECASE))
            for section in possible_sections:
                 if section.find('input', attrs={'name': re.compile(r'brand', re.IGNORECASE)}) or \
                    len(section.find_all(['label', 'li', 'div'], class_=re.compile(r'checkbox|facet-value', re.IGNORECASE))) > 3:
                    brand_section = section
                    st.info(f"Genel aramada olası filtre bölümü bulundu: <{brand_section.name} class='{brand_section.get('class', 'N/A')}'>")
                    break
        if not brand_section:
            st.error("Marka filtresi bölümü HTML içinde bulunamadı (Alternatif Yöntem).")
            return None

        brand_items = brand_section.find_all(['div', 'li', 'label'], class_=re.compile(r'checkbox|facet-value|filter-value|facet-label', re.IGNORECASE))
        if not brand_items:
             inputs = brand_section.find_all('input', type='checkbox', attrs={'name': re.compile(r'brand', re.IGNORECASE)})
             brand_items = [inp.parent for inp in inputs if inp.parent]

        if not brand_items:
            st.error("Marka listesi elementleri (item/label) bulunamadı.")
            return None

        st.info(f"Bulunan olası marka elementi sayısı: {len(brand_items)}")
        extracted_brands = set()
        for item in brand_items:
            brand_name = ""
            count = 0
            text_content = item.get_text(separator=' ', strip=True)
            match = re.search(r'^(.*?)\s*\(?(\d+)\)?$', text_content)
            if match:
                brand_name = match.group(1).strip()
                count = int(match.group(2))
                if brand_name.lower() not in ['no', 'yes', ''] and brand_name not in extracted_brands:
                    brands_data.append({'Marka': brand_name,'Ürün Sayısı': count})
                    extracted_brands.add(brand_name)
            else:
                brand_span = item.find(['label','span'], class_=re.compile(r'label|name', re.IGNORECASE))
                count_span = item.find('span', class_=re.compile(r'count|hitcount', re.IGNORECASE))
                if brand_span and count_span:
                     brand_name = brand_span.get_text(strip=True)
                     count_text = count_span.get_text(strip=True).strip('()[]')
                     if count_text.isdigit():
                         if brand_name.lower() not in ['no', 'yes', ''] and brand_name not in extracted_brands:
                             brands_data.append({'Marka': brand_name, 'Ürün Sayısı': int(count_text)})
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
    # ... (Bu fonksiyon öncekiyle aynı) ...
    if not html_content:
        st.error("HTML içeriği alınamadı.")
        return None

    soup = BeautifulSoup(html_content, 'lxml')
    brands_data = []

    script_tag = soup.find('script', id='__NEXT_DATA__')
    if script_tag:
        st.info("__NEXT_DATA__ script'i bulundu, işleniyor...")
        try:
            next_data = json.loads(script_tag.string)
            brand_filter = find_brand_filter(next_data)

            if brand_filter and 'values' in brand_filter and isinstance(brand_filter['values'], list):
                processed_brands = set()
                for item in brand_filter['values']:
                    if isinstance(item, dict) and 'label' in item and 'hitCount' in item and item['label'] and item['hitCount'] is not None:
                        brand_name = item['label'].strip()
                        if brand_name.lower() != 'no' and brand_name not in processed_brands:
                             brands_data.append({'Marka': brand_name,'Ürün Sayısı': item['hitCount']})
                             processed_brands.add(brand_name)
                if brands_data:
                     st.success(f"{len(brands_data)} marka verisi __NEXT_DATA__ içinden başarıyla çekildi.")
                     return pd.DataFrame(brands_data)
                else:
                     st.warning("__NEXT_DATA__ içinde marka verisi bulundu ancak işlenebilir formatta değildi veya sadece 'No' etiketleri vardı. Alternatif yöntem deneniyor...")
            else:
                st.warning("__NEXT_DATA__ içinde 'c_brand' attributeId'li veya 'values' listesi içeren geçerli yapı bulunamadı. Alternatif yöntem deneniyor...")
        except Exception as e:
            st.error(f"__NEXT_DATA__ işlenirken hata: {e}. Alternatif yöntem deneniyor...")
    else:
        st.warning("__NEXT_DATA__ script'i bulunamadı. Alternatif yöntem deneniyor...")

    if not brands_data:
        return extract_brands_directly(soup)
    else:
        return pd.DataFrame(brands_data)

# --- Streamlit Arayüzü ---
url = st.text_input("Sephora Ürün Listeleme Sayfası URL'sini Girin:", placeholder="https://www.sephora.me/ae-en/shop/fragrance/C301")
process_button = st.button("Markaları Çek ve CSV Oluştur")

if process_button and url:
    if not url.startswith(('http://', 'https://')) or "sephora." not in url:
         st.warning("Lütfen geçerli bir Sephora URL'si girin (http:// veya https:// ile başlamalıdır).")
    else:
        with st.spinner("Sayfa indiriliyor (cloudscraper) ve markalar çekiliyor... Lütfen bekleyin."):
            # Bu sefer cloudscraper ile dene
            html_content = fetch_html_cloudscraper(url)

            if html_content:
                df_brands = extract_brands_from_html(html_content)

                if df_brands is not None and not df_brands.empty:
                    st.subheader("Çekilen Marka Verileri")
                    st.dataframe(df_brands, use_container_width=True)

                    try:
                        csv_buffer = StringIO()
                        df_brands.to_csv(csv_buffer, index=False, encoding='utf-8')
                        csv_data = csv_buffer.getvalue()
                        try:
                            path_part = url.split('/')[-1].split('?')[0]
                            safe_part = re.sub(r'[\\/*?:"<>|]', "-", path_part)
                            safe_part = safe_part[:50] if len(safe_part) > 50 else safe_part
                            csv_filename = f"sephora_markalar_{safe_part}.csv" if safe_part else "sephora_markalar.csv"
                        except Exception:
                            csv_filename = "sephora_markalar.csv"

                        st.download_button(
                            label="💾 CSV Olarak İndir",
                            data=csv_data,
                            file_name=csv_filename,
                            mime='text/csv',
                        )
                    except Exception as e:
                        st.error(f"CSV dosyası oluşturulurken veya indirme butonu hazırlanırken hata: {e}")

                elif df_brands is not None and df_brands.empty:
                     st.warning("Marka verisi bulunamadı. URL'yi, filtrelerin görünürlüğünü kontrol edin veya sayfa yapısı değişmiş olabilir.")
            # else: fetch_html_cloudscraper içinde zaten hata mesajı verildi.

elif process_button and not url:
    st.warning("Lütfen bir URL girin.")

st.markdown("---")
st.caption("Not: Bu uygulama Sephora web sitesinin yapısına bağlıdır. Site güncellenirse veya güvenlik önlemleri (WAF vb.) kullanılırsa veri çekme işlemi başarısız olabilir.")
