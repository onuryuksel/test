import streamlit as st
import pandas as pd
import re
import json # Sadece hata durumunda JSON ayrıştırmayı denemek için kullanılabilir
from bs4 import BeautifulSoup # Artık ana ayrıştırma için kullanılmayacak ama güvenlik için kalabilir
import io

st.set_page_config(page_title="Sephora Marka Çıkarıcı", layout="wide")

st.title("💄 Sephora Marka Filtresi Veri Çıkarıcı")
st.write("Lütfen Sephora ürün listeleme sayfasının indirilmiş HTML dosyasını yükleyin.")
st.caption("Örnek dosya: 'Makeup Essentials_ Lips, Eyes & Skin ≡ Sephora.html'")

def looks_like_brand(label: str) -> bool:
    """
    Verilen metnin bir marka ismine benzeyip benzemediğini kontrol eder.
    (Harf içermeli, rakam içermemeli gibi basit kurallar)
    """
    if not label:
        return False
    # En az bir harf içermeli
    has_letter = any(c.isalpha() for c in label)
    # Rakam içermemeli (Marka isimlerinde genelde olmaz)
    has_digit = any(c.isdigit() for c in label)
    # Çok kısa olmamalı (Tek harfli markalar nadirdir)
    is_long_enough = len(label) > 1
    # Belki sadece büyük harf kontrolü? (Bu siteye özel olabilir, isteğe bağlı)
    # is_mostly_upper = label.isupper() or not any(c.islower() for c in label if c.isalpha())

    # return has_letter and not has_digit and is_long_enough and is_mostly_upper
    return has_letter and not has_digit and is_long_enough

def extract_brands_from_html_text(html_text):
    """
    Parses HTML content as plain text, finds brand/count pairs using regex directly
    within escaped JavaScript string literals, filters, and deduplicates.

    Args:
        html_text (str): The HTML content as a string.

    Returns:
        tuple: A tuple containing (list of brand dictionaries, list of headers)
               or (None, None) if data extraction fails.
    """
    brands_data = []
    fieldnames = ['Marka', 'Urun Adedi']

    # Regex: Kaçış karakterli tırnakları içeren "hitCount": sayı , "label":"marka" kalıbını ara
    # Grup 1: Sayı (\d+)
    # Grup 2: Marka adı ([^"\\]+) - Tırnak veya ters eğik çizgi olmayan karakterler
    pattern = re.compile(r'\\"hitCount\\"\s*:\s*(\d+)\s*,*\s*\\"label\\"\s*:\s*\\"([^"\\]+)\\"', re.IGNORECASE)
    # Alternatif (label önce gelirse):
    pattern_alt = re.compile(r'\\"label\\"\s*:\s*\\"([^"\\]+)\\"\s*,*\s*\\"hitCount\\"\s*:\s*(\d+)', re.IGNORECASE)


    st.write("HTML metni içinde marka/ürün sayısı çiftleri aranıyor...")
    matches = pattern.findall(html_text)
    matches_alt = pattern_alt.findall(html_text)

    st.info(f"İlk desenle {len(matches)} eşleşme, ikinci desenle {len(matches_alt)} eşleşme bulundu.")

    # İki desenden gelen sonuçları birleştir (label, count sırasında)
    all_potential_matches = []
    if matches:
        # (count, label) formatında, (label, count) formatına çevir
        all_potential_matches.extend([(label, count_str) for count_str, label in matches])
    if matches_alt:
         # Zaten (label, count) formatında
        all_potential_matches.extend([(label, count_str) for label, count_str in matches_alt])

    st.write(f"Toplam {len(all_potential_matches)} potansiyel eşleşme işleniyor...")

    brand_totals: dict[str, int] = {}
    processed_count = 0
    skipped_count = 0

    for label, count_str in all_potential_matches:
        # Heuristic filtrelemeyi uygula
        if looks_like_brand(label):
            try:
                count = int(count_str)
                processed_count += 1
                # Tekilleştirme ve maksimum sayıyı tutma
                brand_name = label.strip() # Başındaki/sonundaki boşlukları temizle
                brand_totals[brand_name] = max(brand_totals.get(brand_name, 0), count)
            except ValueError:
                skipped_count += 1
                # st.warning(f"Sayıya dönüştürülemedi: '{count_str}' (Marka: '{label}')") # Debug
        else:
            skipped_count += 1
            # st.write(f"Markaya benzemediği için atlandı: '{label}'") # Debug

    st.write(f"{processed_count} olası marka işlendi, {skipped_count} tanesi filtreye takıldı/hatalıydı.")

    if not brand_totals:
        st.error("Regex ile eşleşen ve marka filtresine uyan veri bulunamadı. HTML kaynağını kontrol edin veya regex desenini/filtreleme kurallarını gözden geçirin.")
        return None, None

    # Sözlüğü listeye çevir
    brands_data = [{"Marka": brand, "Urun Adedi": count} for brand, count in brand_totals.items()]

    st.info(f"Toplam {len(brands_data)} benzersiz marka bulundu.")
    return brands_data, fieldnames

# --- Streamlit File Uploader ---
uploaded_file = st.file_uploader("HTML Dosyasını Buraya Sürükleyin veya Seçin", type=["html", "htm"])

if uploaded_file is not None:
    try:
        # Dosyayı doğrudan metin olarak oku
        html_content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
        st.success(f"'{uploaded_file.name}' başarıyla yüklendi ve okundu.")

        with st.spinner("Marka verileri çıkarılıyor..."):
            # Yeni fonksiyonu çağır
            brands_data, headers = extract_brands_from_html_text(html_content)

        if brands_data and headers:
            st.success("Marka verileri başarıyla çıkarıldı!")
            df = pd.DataFrame(brands_data)
            # Markaya göre sırala
            df = df.sort_values(by='Marka').reset_index(drop=True)
            st.dataframe(df, use_container_width=True)
            csv_string = df.to_csv(index=False, encoding='utf-8-sig') # Excel uyumluluğu için
            st.download_button(
               label="CSV Olarak İndir",
               data=csv_string,
               file_name='sephora_markalar.csv',
               mime='text/csv',
            )
        # else: # Hata mesajı zaten fonksiyon içinde veriliyor

    except UnicodeDecodeError:
        st.error("Dosya kodlaması UTF-8 değil gibi görünüyor. Lütfen UTF-8 formatında kaydedilmiş bir HTML dosyası yükleyin.")
    except Exception as e:
        st.error(f"Dosya işlenirken genel bir hata oluştu: {e}")
        st.exception(e) # Detaylı hata izi için
else:
    st.info("HTML dosyası bekleniyor...")
