import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import json
from io import StringIO  # CSV indirme için gerekli

# Sayfa Başlığı
st.set_page_config(page_title="Sephora Marka Filtre Çekici", layout="wide")
st.title("💄 Sephora Marka Filtre Veri Çekici")
st.caption("Sephora ürün listeleme sayfası linkini girerek marka filtresindeki verileri CSV olarak indirin.")

# --- Fonksiyonlar ---
def fetch_html(url):
    """Verilen URL'den HTML içeriğini çeker."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()  # HTTP hatalarını kontrol et (4xx veya 5xx)
        return response.text
    except requests.exceptions.Timeout:
        st.error(f"İstek zaman aşımına uğradı: {url}")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"URL alınırken hata oluştu: {e}")
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
        # Alternatif Yöntem: HTML içindeki filter yapısını arama (daha az güvenilir)
        return extract_brands_directly(soup)


    try:
        # Script içeriğini JSON olarak parse et
        next_data = json.loads(script_tag.string)
        # Veri yapısı değişebilir, doğru yolu bulmak için inspect gerekebilir.
        # Örnek yapıda props.pageProps.initialState... gibi bir yol izlenebilir.
        # Burada daha genel bir arama yapıyoruz.

        # Çok katmanlı JSON içinde 'attributeId': 'c_brand' içeren objeyi bul
        brand_filter = find_brand_filter(next_data)

        if brand_filter and 'values' in brand_filter:
            for item in brand_filter['values']:
                if 'label' in item and 'hitCount' in item and item['label'] and item['hitCount'] is not None:
                    brands_data.append({
                        'Marka': item['label'],
                        'Ürün Sayısı': item['hitCount']
                    })
            st.success(f"{len(brands_data)} marka verisi __NEXT_DATA__ içinden başarıyla çekildi.")
            return pd.DataFrame(brands_data)
        else:
            st.warning("__NEXT_DATA__ içinde marka filtresi bulunamadı. Alternatif yöntem deneniyor...")
            return extract_brands_directly(soup)

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        st.error(f"__NEXT_DATA__ parse edilirken hata: {e}. Alternatif yöntem deneniyor...")
        return extract_brands_directly(soup)
    except Exception as e:
         st.error(f"Markaları çekerken beklenmedik bir hata oluştu: {e}. Alternatif yöntem deneniyor...")
         return extract_brands_directly(soup)

def find_brand_filter(data):
    """Recursive olarak JSON/dictionary içinde 'attributeId': 'c_brand' arar."""
    if isinstance(data, dict):
        if data.get('attributeId') == 'c_brand' and 'values' in data:
            return data
        for key, value in data.items():
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
    # Tarayıcı Geliştirici Araçları ile filtre bölümünün container'ını ve
    # marka/sayı elementlerini bulup uygun seçicileri belirlemek gerekir.
    # Örnek (Bu seçiciler SADECE TAHMİNİDİR ve çalışmayabilir):
    try:
        # Marka filtresinin genel container'ını bulmaya çalışalım (class adı değişebilir)
        # Genellikle 'Brands' başlığını içeren bir div'in kardeş veya ebeveyn elementi olabilir.
        brand_section = soup.find('h3', string='Brands') # Veya 'h2', 'div' vb. olabilir
        if not brand_section:
             # Belki de input'ların olduğu bir div'i bulabiliriz
             st.warning("Doğrudan HTML'de 'Brands' başlığı bulunamadı.")
             filter_containers = soup.find_all('div', class_=re.compile(r'filter-section|facet-container')) # Regex ile olası class'ları ara
             if not filter_containers:
                 st.error("Marka filtresi bölümü HTML içinde bulunamadı (Alternatif Yöntem).")
                 return None

             # Bu container'lar içinde checkbox ve label'ları arayalım
             for container in filter_containers:
                 items = container.find_all('div', class_=re.compile(r'filter-item|facet-value')) # Örnek class adları
                 if items:
                      brand_section = container # İlk uygun container'ı alalım
                      break

        if not brand_section:
             st.error("Marka filtresi bölümü HTML içinde bulunamadı (Alternatif Yöntem).")
             return None

        # Marka listesini içeren daha spesifik bir parent element arayalım
        parent_element = brand_section.find_parent('div') # Veya 'ul'

        # Marka checkbox'larını veya label'larını bulalım
        # input'un kardeş label'ı veya parent'ı olabilir. Yapıyı incelemek şart.
        # Örnek 1: <label><input ...> Marka (Sayı)</label>
        # Örnek 2: <div><input ...><span>Marka</span><span>(Sayı)</span></div>

        # Örnek 1'e benzer bir yapı arayalım
        labels = parent_element.find_all('label', class_=re.compile(r'checkbox-label|facet-label'))

        if not labels:
            # Örnek 2'ye benzer bir yapı arayalım
            list_items = parent_element.find_all('div', class_=re.compile(r'checkbox-item|facet-item'))
            for item in list_items:
                checkbox = item.find('input', type='checkbox')
                spans = item.find_all('span')
                if checkbox and len(spans) >= 2:
                    brand_name = spans[0].get_text(strip=True)
                    count_text = spans[1].get_text(strip=True).strip('()')
                    if count_text.isdigit():
                         brands_data.append({
                            'Marka': brand_name,
                            'Ürün Sayısı': int(count_text)
                         })

        else: # Label tabanlı yapı
            for label in labels:
                 text = label.get_text(strip=True)
                 # Marka adını ve sayısını ayıklamak için regex
                 match = re.search(r'^(.*?)\s*\((\d+)\)$', text)
                 if match:
                     brand_name = match.group(1).strip()
                     count = int(match.group(2))
                     brands_data.append({
                         'Marka': brand_name,
                         'Ürün Sayısı': count
                     })

        if brands_data:
            st.success(f"{len(brands_data)} marka verisi doğrudan HTML'den başarıyla çekildi (Alternatif Yöntem).")
            return pd.DataFrame(brands_data)
        else:
            st.error("Marka verisi doğrudan HTML elementlerinden de çekilemedi.")
            return None

    except Exception as e:
        st.error(f"Markaları doğrudan HTML'den çekerken hata oluştu (Alternatif Yöntem): {e}")
        return None

# --- Streamlit Arayüzü ---
url = st.text_input("Sephora Ürün Listeleme Sayfası URL'sini Girin:", placeholder="https://www.sephora.ae/en/shop/makeup/C302")
process_button = st.button("Markaları Çek ve CSV Oluştur")

if process_button and url:
    if "sephora." not in url:
         st.warning("Lütfen geçerli bir Sephora URL'si girin.")
    else:
        with st.spinner("Sayfa indiriliyor ve markalar çekiliyor... Lütfen bekleyin."):
            html_content = fetch_html(url)

            if html_content:
                df_brands = extract_brands_from_html(html_content)

                if df_brands is not None and not df_brands.empty:
                    st.subheader("Çekilen Marka Verileri")
                    st.dataframe(df_brands, use_container_width=True)

                    # CSV İndirme Butonu
                    csv_buffer = StringIO()
                    df_brands.to_csv(csv_buffer, index=False, encoding='utf-8')
                    csv_data = csv_buffer.getvalue()

                    # URL'den dosya adı oluşturma (basit)
                    try:
                        file_name_part = url.split('/')[-1].split('?')[0]
                        csv_filename = f"sephora_markalar_{file_name_part}.csv"
                    except:
                        csv_filename = "sephora_markalar.csv"


                    st.download_button(
                        label="💾 CSV Olarak İndir",
                        data=csv_data,
                        file_name=csv_filename,
                        mime='text/csv',
                    )
                elif df_brands is not None and df_brands.empty:
                     st.warning("Marka verisi bulunamadı. Filtreler yüklenmemiş olabilir veya sayfa yapısı farklı olabilir.")
                # Hata mesajları zaten fonksiyon içinde verildi.
            # else: HTML alınamadıysa hata zaten verildi.
elif process_button and not url:
    st.warning("Lütfen bir URL girin.")

st.markdown("---")
st.caption("Not: Bu uygulama Sephora web sitesinin yapısına bağlıdır. Site güncellenirse çalışmayabilir.")
