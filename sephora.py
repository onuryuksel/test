import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import json
from io import StringIO  # CSV indirme için gerekli
# import time # Gerekirse gecikme eklemek için

# Sayfa Başlığı
st.set_page_config(page_title="Sephora Marka Filtre Çekici", layout="wide")
st.title("💄 Sephora Marka Filtre Veri Çekici 1")
st.caption("Sephora ürün listeleme sayfası linkini girerek marka filtresindeki verileri CSV olarak indirin.")

# --- Fonksiyonlar ---

def fetch_html(url):
    """Verilen URL'den HTML içeriğini çeker (Gelişmiş Headers ile)."""
    headers = {
        # Güncel ve yaygın bir User-Agent kullanalım
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
        # Tarayıcıların genellikle gönderdiği diğer başlıklar
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
        'Accept-Language': 'en-US,en;q=0.9,tr;q=0.8', # tr: Türkçe tercihini belirtir
        'Accept-Encoding': 'gzip, deflate, br', # Sıkıştırılmış içeriği kabul ettiğimizi belirtir
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none', # İlk istekte genellikle 'none' olur
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
        # Referer eklemek bazen işe yarayabilir (isteğe bağlı)
        # 'Referer': 'https://www.google.com/'
    }
    try:
        # time.sleep(1) # Çoklu isteklerde rate limiting'e takılmamak için gerekebilir
        # Timeout süresini biraz artırabiliriz
        response = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
        response.raise_for_status() # HTTP hatalarını kontrol et (4xx veya 5xx)

        # İçeriğin boş olup olmadığını kontrol et
        if not response.content:
             st.warning(f"URL'den boş içerik alındı: {url}. Sayfa yapısı veya yükleme sorunu olabilir.")
             return None

        # İçeriği doğru şekilde decode etmeye çalışalım
        response.encoding = response.apparent_encoding or 'utf-8'
        st.success(f"URL başarıyla alındı: {url}") # Başarı mesajı eklendi
        return response.text

    except requests.exceptions.Timeout:
        st.error(f"İstek zaman aşımına uğradı (Timeout=20s): {url}")
        return None
    except requests.exceptions.HTTPError as e:
         # Sunucudan gelen hatayı daha detaylı gösterelim
         st.error(f"HTTP Hatası: {e.response.status_code} {e.response.reason} - URL: {url}")
         # st.error(f"Sunucu Yanıtı (ilk 500 karakter): {e.response.text[:500]}...") # Hassas veri içerebilir, dikkatli kullanın
         return None
    except requests.exceptions.ConnectionError as e:
        # Bu, bizim aldığımız hatayı da kapsar
        st.error(f"Bağlantı Hatası: {e}")
        st.info("Bu hata genellikle sunucunun isteği engellediği (WAF/güvenlik önlemi), geçici ağ sorunları olduğu veya URL'nin hatalı olduğu anlamına gelir. Lütfen URL'yi tarayıcıda kontrol edin ve bir süre sonra tekrar deneyin.")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Genel URL alınırken hata oluştu: {e}")
        return None

def find_brand_filter(data):
    """Recursive olarak JSON/dictionary içinde 'attributeId': 'c_brand' arar."""
    if isinstance(data, dict):
        if data.get('attributeId') == 'c_brand' and 'values' in data:
            # Değerlerin listesi boş değilse ve içinde beklenen yapı varsa döndür
            if data['values'] and isinstance(data['values'], list) and all(isinstance(item, dict) for item in data['values']):
                 return data
        for key, value in data.items():
            # 'image' veya benzeri büyük/gereksiz alanları atla (performans için)
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
    """
    Alternatif yöntem: Doğrudan HTML elementlerini parse etmeye çalışır.
    Bu yöntem sayfa yapısı değişirse kolayca bozulabilir.
    """
    st.info("Alternatif yöntem: HTML elementleri taranıyor...")
    brands_data = []
    try:
        # Genellikle filtreler bir tür 'facet' veya 'filter' container'ı içinde bulunur.
        # 'Brands' başlığını içeren div'i veya h3'ü bulup onun parent'ına bakmak iyi bir başlangıç olabilir.
        # Tarayıcı geliştirici araçlarıyla spesifik class'ları veya ID'leri belirlemek en doğrusu.
        brand_header = soup.find(['h3', 'h2', 'div'], string=re.compile(r'Brands', re.IGNORECASE))

        if not brand_header:
            st.warning("Doğrudan HTML'de 'Brands' başlığı bulunamadı. Daha genel filtre container'ları aranıyor...")
            # Genel filtre container'larını ara
            filter_containers = soup.find_all('div', class_=re.compile(r'filter-section|facet-container|refinement-options', re.IGNORECASE))
            if not filter_containers:
                 st.error("Marka filtresi bölümü HTML içinde bulunamadı (Alternatif Yöntem).")
                 return None
            # İçinde checkbox input olan ilk container'ı seçmeye çalışalım
            brand_section = None
            for container in filter_containers:
                if container.find('input', type='checkbox', attrs={'name': re.compile(r'brand|Brand', re.IGNORECASE)}):
                    brand_section = container
                    st.info(f"Olası marka filtre container'ı bulundu: {container.get('class', 'N/A')}")
                    break
            if not brand_section:
                st.error("Checkbox içeren marka filtresi container'ı bulunamadı.")
                return None
        else:
             # Başlıktan yola çıkarak parent elementi bul
             # Bu yapı siteye göre çok değişir (örnek: başlığın 2 üst parent'ı olabilir)
             brand_section = brand_header.find_parent('div', class_=re.compile(r'filter-section|facet-container|refinement-options', re.IGNORECASE))
             if not brand_section:
                 brand_section = brand_header.find_parent('div').find_parent('div') # Örnek deneme
             if not brand_section:
                 st.error("Marka başlığından yola çıkarak filtre bölümü bulunamadı.")
                 return None
             st.info(f"Marka başlığından yola çıkarak filtre container'ı bulundu: {brand_section.get('class', 'N/A')}")


        # Marka checkbox'larını veya bunları içeren div'leri bul
        # Class isimleri çok değişkendir, regex ile daha esnek arama yapıyoruz
        brand_items = brand_section.find_all('div', class_=re.compile(r'checkbox-item|facet-value|filter-value', re.IGNORECASE))

        if not brand_items:
             # Belki de doğrudan label içindedirler
             brand_items = brand_section.find_all('label', class_=re.compile(r'checkbox-label|facet-label', re.IGNORECASE))

        if not brand_items:
            st.error("Marka listesi elementleri (item/label) bulunamadı.")
            return None

        st.info(f"Bulunan olası marka elementi sayısı: {len(brand_items)}")

        for item in brand_items:
            brand_name = ""
            count = 0

            # Label içindeki metni dene
            text_content = item.get_text(separator=' ', strip=True)

            # Regex ile "Marka Adı (Sayı)" formatını ara
            match = re.search(r'^(.*?)\s*\((\d+)\)$', text_content)
            if match:
                brand_name = match.group(1).strip()
                count = int(match.group(2))
                if brand_name == "No": # "No (2048)" gibi durumları elemek için
                    continue
                brands_data.append({
                    'Marka': brand_name,
                    'Ürün Sayısı': count
                })
            else:
                # Eşleşme olmazsa, belki sayı ayrı bir span içindedir (daha az olası)
                brand_span = item.find('span', class_=re.compile(r'label|name', re.IGNORECASE))
                count_span = item.find('span', class_=re.compile(r'count|hitcount', re.IGNORECASE))
                if brand_span and count_span:
                     brand_name = brand_span.get_text(strip=True)
                     count_text = count_span.get_text(strip=True).strip('()')
                     if count_text.isdigit():
                         if brand_name == "No": continue
                         brands_data.append({
                            'Marka': brand_name,
                            'Ürün Sayısı': int(count_text)
                         })

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
    """
    HTML içeriğinden __NEXT_DATA__ script'ini bularak marka verilerini çıkarır.
    Sephora'nın Next.js kullandığı ve veriyi script tag'ine gömdüğü varsayılır.
    """
    if not html_content:
        return None

    soup = BeautifulSoup(html_content, 'lxml') # lxml parser kullanıyoruz
    brands_data = []

    # Next.js'in veri gömdüğü script tag'ini bul
    script_tag = soup.find('script', id='__NEXT_DATA__')

    if not script_tag:
        st.warning("Sayfa yapısı beklenenden farklı. __NEXT_DATA__ script'i bulunamadı. Alternatif yöntem deneniyor...")
        return extract_brands_directly(soup) # Alternatif yönteme geç

    try:
        # Script içeriğini JSON olarak parse et
        next_data = json.loads(script_tag.string)

        # Çok katmanlı JSON içinde 'attributeId': 'c_brand' içeren objeyi bul
        # 'props.pageProps.initialState...' gibi yollar yerine genel arama yapıyoruz
        brand_filter = find_brand_filter(next_data)

        if brand_filter and 'values' in brand_filter and isinstance(brand_filter['values'], list):
            for item in brand_filter['values']:
                # Öğenin dictionary olduğunu ve gerekli anahtarları içerdiğini kontrol et
                if isinstance(item, dict) and 'label' in item and 'hitCount' in item and item['label'] and item['hitCount'] is not None:
                    # "No" gibi anlamsız etiketleri filtrele (hitCount'a göre değil, isme göre)
                    if item['label'].strip().lower() != 'no':
                         brands_data.append({
                            'Marka': item['label'],
                            'Ürün Sayısı': item['hitCount']
                         })
            if brands_data:
                 st.success(f"{len(brands_data)} marka verisi __NEXT_DATA__ içinden başarıyla çekildi.")
                 return pd.DataFrame(brands_data)
            else:
                 st.warning("__NEXT_DATA__ içinde marka verisi bulundu ancak işlenebilir formatta değildi veya 'No' etiketleri vardı. Alternatif yöntem deneniyor...")
                 return extract_brands_directly(soup) # Alternatif yönteme geç
        else:
            st.warning("__NEXT_DATA__ içinde 'c_brand' attributeId'li veya 'values' listesi içeren geçerli yapı bulunamadı. Alternatif yöntem deneniyor...")
            return extract_brands_directly(soup) # Alternatif yönteme geç

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        st.error(f"__NEXT_DATA__ parse edilirken veya işlenirken hata: {e}. Alternatif yöntem deneniyor...")
        return extract_brands_directly(soup) # Alternatif yönteme geç
    except Exception as e:
         st.error(f"Markaları çekerken beklenmedik bir hata oluştu: {e}. Alternatif yöntem deneniyor...")
         return extract_brands_directly(soup) # Alternatif yönteme geç


# --- Streamlit Arayüzü ---
url = st.text_input("Sephora Ürün Listeleme Sayfası URL'sini Girin:", placeholder="https://www.sephora.ae/en/shop/makeup/C302")
process_button = st.button("Markaları Çek ve CSV Oluştur")

if process_button and url:
    # Basit URL doğrulaması
    if not url.startswith(('http://', 'https://')) or "sephora." not in url:
         st.warning("Lütfen geçerli bir Sephora URL'si girin (http:// veya https:// ile başlamalıdır).")
    else:
        with st.spinner("Sayfa indiriliyor ve markalar çekiliyor... Lütfen bekleyin."):
            html_content = fetch_html(url)

            if html_content:
                df_brands = extract_brands_from_html(html_content)

                if df_brands is not None and not df_brands.empty:
                    st.subheader("Çekilen Marka Verileri")
                    st.dataframe(df_brands, use_container_width=True)

                    # CSV İndirme Butonu
                    try:
                        csv_buffer = StringIO()
                        # UTF-8 BOM (Byte Order Mark) ekleyerek Excel uyumluluğunu artırabiliriz
                        # df_brands.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                        df_brands.to_csv(csv_buffer, index=False, encoding='utf-8')
                        csv_data = csv_buffer.getvalue()

                        # URL'den dosya adı oluşturma (daha sağlam)
                        try:
                            # URL'nin son kısmını al (sorgu parametrelerini kaldır)
                            path_part = url.split('/')[-1].split('?')[0]
                            # Geçersiz karakterleri kaldır veya değiştir
                            safe_part = re.sub(r'[\\/*?:"<>|]', "-", path_part)
                            # Çok uzunsa kısalt
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
                # else: extract_brands_from_html içinde zaten hata mesajı verildi.
            # else: fetch_html içinde zaten hata mesajı verildi.

elif process_button and not url:
    st.warning("Lütfen bir URL girin.")

st.markdown("---")
st.caption("Not: Bu uygulama Sephora web sitesinin yapısına bağlıdır. Site güncellenirse veya güvenlik önlemleri artırılırsa çalışmayabilir.")
