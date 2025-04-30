import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import csv
import io

# --- Veri Çıkarma Fonksiyonu (Flask versiyonundan uyarlanmış) ---
def extract_designers_from_url(url):
    """
    Verilen URL'den HTML'i çeker, __NEXT_DATA__ JSON'unu çıkarır
    ve designer/brand filtresindeki verileri döndürür.

    Args:
        url (str): Level Shoes PLP URL'si.

    Returns:
        list: Başarılı olursa [['Designer', 'Count'], ['Marka1', Sayı1], ...] listesi.
        str: Hata veya uyarı mesajı.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        # Timeout ekleyerek isteği yap
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status() # HTTP hatalarını kontrol et
    except requests.exceptions.Timeout:
        return "Hata: İstek zaman aşımına uğradı. URL'yi kontrol edin veya sonra tekrar deneyin."
    except requests.exceptions.RequestException as e:
        return f"Hata: URL alınırken bir sorun oluştu: {e}"
    except Exception as e:
        return f"Hata: Beklenmedik bir ağ hatası oluştu: {e}"

    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        script_tag = soup.find('script', {'id': '__NEXT_DATA__'})

        if not script_tag:
            return "Hata: Sayfa yapısı beklenenden farklı, '__NEXT_DATA__' bulunamadı."

        json_data_str = script_tag.string
        if not json_data_str:
            return "Hata: __NEXT_DATA__ içeriği boş."

        data = json.loads(json_data_str)

        # JSON yapısını güvenli bir şekilde gezin
        apollo_state = data.get('props', {}).get('pageProps', {}).get('__APOLLO_STATE__', {})
        root_query = apollo_state.get('ROOT_QUERY', {})

        product_list_key = next((key for key in root_query if key.startswith('_productList')), None)

        if not product_list_key:
             # Alternatif anahtar yapısını deneyelim (Bazen anahtar ID içerebilir)
             product_list_key = next((key for key in root_query if '_productList:({' in key), None)
             if not product_list_key:
                 st.json(root_query.keys()) # Hata ayıklama için anahtarları göster
                 return "Hata: Gerekli ürün listesi verisi sayfada bulunamadı (product list key)."


        facets = root_query.get(product_list_key, {}).get('facets', [])

        designer_facet = None
        for facet in facets:
            # 'brand' veya 'designer' anahtarını arayalım
            if facet.get('key') == 'brand' or facet.get('label', '').lower() == 'designer':
                designer_facet = facet
                break

        if not designer_facet:
            # Hata ayıklama için mevcut facet'leri gösterelim
            available_facets = [f.get('key') or f.get('label') for f in facets]
            st.write("Bulunan Filtre Anahtarları/Etiketleri:", available_facets)
            return "Hata: Sayfada 'brand' veya 'Designer' filtresi bulunamadı."

        designer_options = designer_facet.get('options', [])

        if not designer_options:
            return "Uyarı: Tasarımcı filtresinde hiç seçenek bulunamadı."

        # CSV için veriyi hazırla
        csv_data = [['Designer', 'Count']]
        for option in designer_options:
            name = option.get('name')
            count = option.get('count')
            if name is not None and count is not None:
                csv_data.append([name, count])

        if len(csv_data) <= 1:
             return "Uyarı: Tasarımcı verisi bulundu ancak liste boş."

        return csv_data

    except json.JSONDecodeError:
        return "Hata: Sayfadan alınan veri JSON formatında değil."
    except (AttributeError, KeyError, TypeError, IndexError) as e:
        st.error(f"İşleme hatası detayı: {e}") # Geliştirme için loglama
        return "Hata: Sayfa yapısı değişmiş olabilir veya beklenmeyen bir veri yapısı ile karşılaşıldı."
    except Exception as e:
        st.exception(e) # Geliştirme için tam hata izini göster
        return f"Hata: Veri işlenirken beklenmedik bir sorun oluştu: {e}"

# --- CSV Dönüştürme Fonksiyonu ---
def convert_to_csv(data):
    """Verilen listeyi CSV formatında string'e çevirir."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(data)
    return output.getvalue()

# --- Streamlit Uygulama Arayüzü ---
st.set_page_config(page_title="Level Shoes Extractor", layout="wide")
st.title("👠 Level Shoes Designer Extractor")
st.markdown("Bir Level Shoes Ürün Listeleme Sayfası (PLP) URL'si girin ve sayfadaki tasarımcı filtresi verilerini CSV olarak alın.")

# Session state kullanarak önceki URL'yi ve veriyi sakla
if 'submitted_url' not in st.session_state:
    st.session_state.submitted_url = ""
if 'designer_data' not in st.session_state:
    st.session_state.designer_data = None
if 'error_message' not in st.session_state:
    st.session_state.error_message = None

url = st.text_input(
    "Level Shoes PLP URL:",
    placeholder="https://www.levelshoes.com/...",
    value=st.session_state.submitted_url,
    key="url_input" # Tekrar renderlamada değeri korumak için anahtar
)

col1, col2 = st.columns([1, 5]) # Butonlar için sütunlar

with col1:
    extract_button = st.button("Veriyi Çıkar", key="extract")

if extract_button:
    if not url:
        st.warning('Lütfen bir URL girin.')
        st.session_state.designer_data = None
        st.session_state.error_message = None
    elif not url.startswith(('http://', 'https://')) or 'levelshoes.com' not in url:
        st.warning('Lütfen geçerli bir Level Shoes URL\'si girin.')
        st.session_state.designer_data = None
        st.session_state.error_message = None
        st.session_state.submitted_url = url # Girilen URL'yi kutuda tut
    else:
        st.session_state.submitted_url = url # Başarılı gönderim için URL'yi sakla
        with st.spinner("Veriler alınıyor ve işleniyor... Lütfen bekleyin."):
            result = extract_designers_from_url(url)
            if isinstance(result, list):
                st.session_state.designer_data = result
                st.session_state.error_message = None
                st.success('Veri başarıyla çıkarıldı!')
            else: # Hata veya uyarı mesajı döndü
                st.session_state.designer_data = None
                st.session_state.error_message = result # Hata mesajını sakla

# --- Sonuçları Göster ve İndirme Butonu ---
if st.session_state.error_message:
    st.error(st.session_state.error_message) # Saklanan hata mesajını göster

if st.session_state.designer_data and isinstance(st.session_state.designer_data, list):
    st.subheader(f"Çıkarılan Tasarımcılar ({len(st.session_state.designer_data) - 1} adet)")

    # Veriyi DataFrame olarak göster
    # İlk satırı (başlık) atlayarak DataFrame oluştur
    if len(st.session_state.designer_data) > 1:
        df_data = {
            st.session_state.designer_data[0][0]: [row[0] for row in st.session_state.designer_data[1:]],
            st.session_state.designer_data[0][1]: [row[1] for row in st.session_state.designer_data[1:]]
        }
        st.dataframe(df_data, use_container_width=True) # Tabloyu göster
    else:
        st.info("Tasarımcı listesi başlık dışında veri içermiyor.")


    # CSV İndirme Butonu
    csv_string = convert_to_csv(st.session_state.designer_data)
    st.download_button(
       label="CSV Olarak İndir",
       data=csv_string,
       file_name='level_shoes_designers.csv',
       mime='text/csv',
       key='download-csv'
    )

st.markdown("---")
st.caption("Not: Bu araç Level Shoes web sitesinin yapısına bağlıdır. Site güncellenirse araç çalışmayabilir.")
