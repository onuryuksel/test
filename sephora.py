import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import json
from io import StringIO
import time # Gerekirse gecikme eklemek için

# Sayfa Başlığı
st.set_page_config(page_title="Sephora Marka Filtre Çekici", layout="wide")
st.title("💄 Sephora Marka Filtre Veri Çekici")
st.caption("Sephora ürün listeleme sayfası linkini girerek marka filtresindeki verileri CSV olarak indirin.")

# --- Fonksiyonlar ---

@st.cache_resource # Session objesini cache'le
def get_session():
    """Tek bir requests.Session nesnesi oluşturur."""
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9,tr-TR;q=0.8,tr;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Sec-Ch-Ua': '"Not.A/Brand";v="8", "Chromium";v="114", "Google Chrome";v="114"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Cache-Control': 'max-age=0',
    }
    session.headers.update(headers)
    return session

def fetch_html_requests(url):
    """Verilen URL'den HTML içeriğini requests.Session ile çeker (Timeout artırıldı)."""
    session = get_session()
    # Timeout süresini 60 saniyeye çıkaralım
    timeout_seconds = 60
    try:
        # time.sleep(0.5)
        st.info(f"URL alınıyor (Timeout={timeout_seconds}s)... Lütfen bekleyin.")
        response = session.get(url, timeout=timeout_seconds, allow_redirects=True)
        response.raise_for_status()

        if not response.content:
             st.warning(f"URL'den boş içerik alındı: {url}. Sayfa yapısı veya engelleme sorunu olabilir.")
             return None

        response.encoding = response.apparent_encoding or 'utf-8'
        st.success(f"URL başarıyla alındı (requests): {url}")
        return response.text

    except requests.exceptions.Timeout:
        st.error(f"İstek zaman aşımına uğradı (Timeout={timeout_seconds}s): {url}")
        st.info("Sunucu yanıt vermedi. Sunucu yoğun olabilir veya istek engelleniyor olabilir.")
        return None
    except requests.exceptions.HTTPError as e:
         st.error(f"HTTP Hatası: {e.response.status_code} {e.response.reason} - URL: {url}")
         if e.response.status_code == 403:
              st.warning("403 Forbidden hatası alındı. Bu genellikle bot koruması anlamına gelir.")
         elif e.response.status_code >= 500:
              st.warning("Sunucu hatası alındı. Site geçici olarak erişilemez olabilir.")
         return None
    except requests.exceptions.ConnectionError as e:
        st.error(f"Bağlantı Hatası: {e}")
        st.info("Bağlantı kurulamadı veya sunucu bağlantıyı kapattı. URL'yi kontrol edin veya ağ sorunlarını/engellemeleri değerlendirin.")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Genel URL alınırken hata oluştu: {e}")
        return None

# --- Marka Çıkarma Fonksiyonları (Önceki kodla aynı) ---

def find_brand_filter(data):
    """Recursive olarak JSON/dictionary içinde 'attributeId': 'c_brand' arar."""
    if isinstance(data, dict):
        if data.get('attributeId') == 'c_brand' and 'values' in data:
            if data['values'] and isinstance(data['values'], list) and all(isinstance(item, dict) for item in data['values']):
                 return data
        for key, value in data.items():
            if key not in ['image', 'images', 'icon', 'icons', 'banner', 'banners', 'variations', 'attributes']: # Büyük listeleri/dict'leri atla
                result = find_brand_filter(value)
                if result:
                    return result
    elif isinstance(data, list):
        # Listeyi küçültme (çok uzun listelerde performansı artırabilir - riskli)
        # items_to_check = data[:500] if len(data) > 500 else data
        items_to_check = data
        for item in items_to_check:
            result = find_brand_filter(item)
            if result:
                return result
    return None

def extract_brands_directly(soup):
    """Alternatif yöntem: Doğrudan HTML elementlerini parse etmeye çalışır."""
    st.info("Alternatif yöntem: HTML elementleri taranıyor...")
    brands_data = []
    try:
        # 'Brands' başlığını veya benzerini bul
        brand_header = soup.find(['h3', 'h2', 'div', 'button'], string=re.compile(r'Brands?', re.IGNORECASE))

        # Filtre container'ını bul
        brand_section = None
        if brand_header:
            # Başlıktan birkaç seviye yukarı çıkmayı dene
            current = brand_header
            for _ in range(5): # En fazla 5 seviye yukarı bak
                 parent = current.find_parent(['div', 'section', 'aside'])
                 if parent and parent.find(['input', 'label'], class_=re.compile(r'checkbox|facet', re.IGNORECASE)):
                      brand_section = parent
                      st.info(f"Başlıktan parent bulundu: <{brand_section.name} class='{brand_section.get('class', 'N/A')}'>")
                      break
                 if not parent: break # Daha fazla parent yoksa dur
                 current = parent

        # Eğer başlıktan bulunamazsa, genel filtre container'larını ara
        if not brand_section:
            st.warning("Marka başlığından filtre bölümü bulunamadı. Genel arama...")
            # Checkbox içeren veya çok sayıda filtre değeri içeren div'leri ara
            possible_sections = soup.find_all('div', class_=re.compile(r'filter|facet|refine', re.IGNORECASE))
            for section in possible_sections:
                # İçinde 'brand' geçen bir input veya çok sayıda checkbox/label var mı?
                 if section.find('input', attrs={'name': re.compile(r'brand', re.IGNORECASE)}) or \
                    len(section.find_all(['label', 'li', 'div'], class_=re.compile(r'checkbox|facet-value', re.IGNORECASE))) > 3: # Eşik değeri
                    brand_section = section
                    st.info(f"Genel aramada olası filtre bölümü bulundu: <{brand_section.name} class='{brand_section.get('class', 'N/A')}'>")
                    break

        if not brand_section:
            st.error("Marka filtresi bölümü HTML içinde bulunamadı (Alternatif Yöntem).")
            return None

        # Marka item'larını bul (label veya input içeren div/li)
        brand_items = brand_section.find_all(['div', 'li', 'label'], class_=re.compile(r'checkbox|facet-value|filter-value|facet-label', re.IGNORECASE))

        if not brand_items:
            # Sadece input'ları bulup parent'larından text almayı dene
            inputs = brand_section.find_all('input', type='checkbox', attrs={'name': re.compile(r'brand', re.IGNORECASE)})
            brand_items = [inp.parent for inp in inputs if inp.parent] # Parent'ları al

        if not brand_items:
            st.error("Marka listesi elementleri (item/label) bulunamadı.")
            return None

        st.info(f"Bulunan olası marka elementi sayısı: {len(brand_items)}")

        extracted_brands = set() # Marka isimlerinin tekrarını önlemek için
        for item in brand_items:
            brand_name = ""
            count = 0
            text_content = item.get_text(separator=' ', strip=True)

            # Regex: Marka Adı (Sayı) veya Marka Adı Sayı
            match = re.search(r'^(.*?)\s*\(?(\d+)\)?$', text_content)
            if match:
                brand_name = match.group(1).strip()
                count = int(match.group(2))
                # Anlamsız isimleri filtrele
                if brand_name.lower() not in ['no', 'yes', ''] and brand_name not in extracted_brands:
                    brands_data.append({'Marka': brand_name,'Ürün Sayısı': count})
                    extracted_brands.add(brand_name)

        if brands_data:
            st.success(f"{len(brands_data)} marka verisi doğrudan HTML'den başarıyla çekildi (Alternatif Yöntem).")
            return pd.DataFrame(brands_data) # Zaten unique olmalı ama emin olmak için drop_duplicates kullanılabilir
        else:
            st.warning("Doğrudan HTML taramasında yapısal marka verisi bulunamadı veya ayıklanamadı.")
            return None

    except Exception as e:
        st.error(f"Markaları doğrudan HTML'den çekerken hata oluştu (Alternatif Yöntem): {e}")
        return None


def extract_brands_from_html(html_content):
    """HTML içeriğinden marka verilerini çıkarır (__NEXT_DATA__ öncelikli)."""
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

    # Alternatif Yöntem
    return extract_brands_directly(soup)


# --- Streamlit Arayüzü ---
url = st.text_input("Sephora Ürün Listeleme Sayfası URL'sini Girin:", placeholder="https://www.sephora.me/ae-en/shop/fragrance/C301")
process_button = st.button("Markaları Çek ve CSV Oluştur")

if process_button and url:
    if not url.startswith(('http://', 'https://')) or "sephora." not in url:
         st.warning("Lütfen geçerli bir Sephora URL'si girin (http:// veya https:// ile başlamalıdır).")
    else:
        with st.spinner("Sayfa indiriliyor (requests) ve markalar çekiliyor... Lütfen bekleyin."):
            # Yeniden requests ile dene (uzun timeout ile)
            html_content = fetch_html_requests(url)

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
            # else: fetch_html_requests içinde hata mesajı zaten verildi.

elif process_button and not url:
    st.warning("Lütfen bir URL girin.")

st.markdown("---")
st.caption("Not: Bu uygulama Sephora web sitesinin yapısına bağlıdır. Site güncellenirse veya güvenlik önlemleri (WAF vb.) kullanılırsa `requests` ile veri çekme işlemi başarısız olabilir.")
