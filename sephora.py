import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import json
from io import StringIO
import time # Küçük bir gecikme ekleyebiliriz

# Sayfa Başlığı
st.set_page_config(page_title="Sephora Marka Filtre Çekici", layout="wide")
st.title("💄 Sephora Marka Filtre Veri Çekici")
st.caption("Sephora ürün listeleme sayfası linkini girerek marka filtresindeki verileri CSV olarak indirin.")

# --- Fonksiyonlar ---

@st.cache_resource # Session objesini cache'le
def get_session():
    """Tek bir requests.Session nesnesi oluşturur."""
    session = requests.Session()
    # Session için varsayılan header'ları ayarla
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36', # Daha güncel bir UA
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9,tr-TR;q=0.8,tr;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Sec-Ch-Ua': '"Not.A/Brand";v="8", "Chromium";v="114", "Google Chrome";v="114"', # Client Hints
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Cache-Control': 'max-age=0',
    }
    session.headers.update(headers)
    return session

def fetch_html_requests(url):
    """Verilen URL'den HTML içeriğini requests.Session ile çeker."""
    session = get_session()
    try:
        # time.sleep(0.5) # Çok nazik bir gecikme
        response = session.get(url, timeout=20, allow_redirects=True) # Session objesi ile get isteği
        response.raise_for_status()

        if not response.content:
             st.warning(f"URL'den boş içerik alındı: {url}. Sayfa yapısı veya engelleme sorunu olabilir.")
             return None

        # İçeriği doğru şekilde decode et
        response.encoding = response.apparent_encoding or 'utf-8'
        st.success(f"URL başarıyla alındı (requests): {url}")
        return response.text

    except requests.exceptions.Timeout:
        st.error(f"İstek zaman aşımına uğradı (Timeout=20s): {url}")
        return None
    except requests.exceptions.HTTPError as e:
         st.error(f"HTTP Hatası: {e.response.status_code} {e.response.reason} - URL: {url}")
         # st.error(f"Sunucu Yanıtı (ilk 500 karakter): {e.response.text[:500]}...")
         if e.response.status_code == 403:
              st.warning("403 Forbidden hatası alındı. Bu genellikle bot koruması anlamına gelir.")
         elif e.response.status_code >= 500:
              st.warning("Sunucu hatası alındı. Site geçici olarak erişilemez olabilir.")
         return None
    except requests.exceptions.ConnectionError as e:
        st.error(f"Bağlantı Hatası: {e}")
        st.info("Bu hata genellikle sunucunun isteği engellediği, geçici ağ sorunları olduğu veya URL'nin hatalı olduğu anlamına gelir. Lütfen URL'yi tarayıcıda kontrol edin.")
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
            if key not in ['image', 'images', 'icon', 'icons', 'banner', 'banners']:
                result = find_brand_filter(value)
                if result:
                    return result
    elif isinstance(data, list):
        for item in data:
            result = find_brand_filter(item)
            if result:
                return result
    return None

def extract_brands_directly(soup):
    """Alternatif yöntem: Doğrudan HTML elementlerini parse etmeye çalışır."""
    st.info("Alternatif yöntem: HTML elementleri taranıyor...")
    brands_data = []
    try:
        brand_header = soup.find(['h3', 'h2', 'div'], string=re.compile(r'Brands', re.IGNORECASE))
        if not brand_header:
            st.warning("Doğrudan HTML'de 'Brands' başlığı bulunamadı. Daha genel filtre container'ları aranıyor...")
            filter_containers = soup.find_all('div', class_=re.compile(r'filter-section|facet-container|refinement-options', re.IGNORECASE))
            if not filter_containers:
                 st.error("Marka filtresi bölümü HTML içinde bulunamadı (Alternatif Yöntem).")
                 return None
            brand_section = None
            for container in filter_containers:
                # Checkbox input'u içeren bir container ara
                if container.find('input', type='checkbox', attrs={'name': re.compile(r'brand|Brand', re.IGNORECASE)}):
                    brand_section = container
                    st.info(f"Olası marka filtre container'ı bulundu: {container.get('class', 'N/A')}")
                    break
                # Veya doğrudan marka listesi gibi görünen bir yapı ara (örneğin, çok sayıda label içeren)
                elif len(container.find_all('label', class_=re.compile(r'checkbox-label|facet-label', re.IGNORECASE))) > 5: # Eşik değeri ayarlanabilir
                    brand_section = container
                    st.info(f"Label içeren olası marka filtre container'ı bulundu: {container.get('class', 'N/A')}")
                    break
            if not brand_section:
                 st.error("Checkbox/Label içeren marka filtresi container'ı bulunamadı.")
                 return None
        else:
             brand_section = brand_header.find_parent('div', class_=re.compile(r'filter-section|facet-container|refinement-options', re.IGNORECASE))
             if not brand_section: brand_section = brand_header.find_parent('div', recursive=False) # Doğrudan parent
             if not brand_section: brand_section = brand_header.find_parent('div').find_parent('div') # İki üst parent
             if not brand_section:
                 st.error("Marka başlığından yola çıkarak filtre bölümü bulunamadı.")
                 return None
             st.info(f"Marka başlığından yola çıkarak filtre container'ı bulundu: {brand_section.get('class', 'N/A')}")

        # Marka item'larını/label'larını bul
        brand_items = brand_section.find_all(['div', 'li', 'label'], class_=re.compile(r'checkbox-item|facet-value|filter-value|checkbox-label|facet-label', re.IGNORECASE))

        if not brand_items:
            st.error("Marka listesi elementleri (item/label) bulunamadı.")
            return None

        st.info(f"Bulunan olası marka elementi sayısı: {len(brand_items)}")

        for item in brand_items:
            brand_name = ""
            count = 0
            text_content = item.get_text(separator=' ', strip=True)
            match = re.search(r'^(.*?)\s*\((\d+)\)$', text_content) # Marka (Sayı) formatı
            if match:
                brand_name = match.group(1).strip()
                count = int(match.group(2))
                if brand_name.lower() == 'no' or not brand_name : continue
                brands_data.append({'Marka': brand_name,'Ürün Sayısı': count})
            else: # Belki sayı ayrı bir span'de
                 brand_span = item.find(['label','span'], class_=re.compile(r'label|name', re.IGNORECASE))
                 count_span = item.find('span', class_=re.compile(r'count|hitcount', re.IGNORECASE))
                 if brand_span and count_span:
                     brand_name = brand_span.get_text(strip=True)
                     count_text = count_span.get_text(strip=True).strip('()[]') # Parantezleri temizle
                     if count_text.isdigit():
                         if brand_name.lower() == 'no' or not brand_name: continue
                         brands_data.append({'Marka': brand_name, 'Ürün Sayısı': int(count_text)})

        if brands_data:
            st.success(f"{len(brands_data)} marka verisi doğrudan HTML'den başarıyla çekildi (Alternatif Yöntem).")
            df = pd.DataFrame(brands_data)
            df_unique = df.drop_duplicates(subset=['Marka'])
            st.info(f"Yinelenenler kaldırıldıktan sonra {len(df_unique)} marka kaldı.")
            return df_unique
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
                for item in brand_filter['values']:
                    if isinstance(item, dict) and 'label' in item and 'hitCount' in item and item['label'] and item['hitCount'] is not None:
                        if item['label'].strip().lower() != 'no':
                             brands_data.append({'Marka': item['label'],'Ürün Sayısı': item['hitCount']})
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

    # __NEXT_DATA__'dan veri alınamazsa veya boşsa, doğrudan HTML'den çekmeyi dene
    if not brands_data:
        return extract_brands_directly(soup)
    else: # __NEXT_DATA__ bulundu ama boştu
        return pd.DataFrame(brands_data)


# --- Streamlit Arayüzü ---
url = st.text_input("Sephora Ürün Listeleme Sayfası URL'sini Girin:", placeholder="https://www.sephora.me/ae-en/shop/fragrance/C301")
process_button = st.button("Markaları Çek ve CSV Oluştur")

if process_button and url:
    if not url.startswith(('http://', 'https://')) or "sephora." not in url:
         st.warning("Lütfen geçerli bir Sephora URL'si girin (http:// veya https:// ile başlamalıdır).")
    else:
        with st.spinner("Sayfa indiriliyor (requests) ve markalar çekiliyor... Lütfen bekleyin."):
            # Önce requests ile dene
            html_content = fetch_html_requests(url)

            if html_content:
                df_brands = extract_brands_from_html(html_content) # HTML'i işle

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
