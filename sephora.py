# (Keep imports and Streamlit setup the same)
import streamlit as st
import pandas as pd
import re
import json
from bs4 import BeautifulSoup
import io

st.set_page_config(page_title="Sephora Marka Çıkarıcı", layout="wide")

st.title("💄 Sephora Marka Filtresi Veri Çıkarıcı121")
st.write("Lütfen Sephora ürün listeleme sayfasının indirilmiş HTML dosyasını yükleyin.")
st.caption("Örnek dosya: 'Makeup Essentials_ Lips, Eyes & Skin ≡ Sephora.html'")

def find_brands_in_json(data):
    """Recursively search for the 'c_brand' attributeId within a parsed JSON object."""
    if isinstance(data, dict):
        if data.get("attributeId") == "c_brand" and "values" in data and isinstance(data["values"], list):
            # Found the target structure, return the values list
            return data["values"]
        # Search deeper in dictionary values
        for value in data.values():
            result = find_brands_in_json(value)
            if result is not None:
                return result
    elif isinstance(data, list):
        # Search deeper in list items
        for item in data:
            result = find_brands_in_json(item)
            if result is not None:
                return result
    # Not found in this branch
    return None

def extract_brands_from_scripts_aggressive_json(html_content):
    """
    Parses HTML content, finds scripts, extracts all potential JSON objects/arrays
    within each script, parses them, and searches for the brand filter data.

    Args:
        html_content (str): The HTML content as a string.

    Returns:
        tuple: A tuple containing (list of brand dictionaries, list of headers)
               or (None, None) if data extraction fails.
    """
    try:
        soup = BeautifulSoup(html_content, 'lxml')
    except Exception as e:
        st.warning(f"lxml parser ile HTML ayrıştırılırken hata (html.parser deneniyor): {e}")
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
        except Exception as e2:
             st.error(f"HTML ayrıştırılamadı: {e2}")
             return None, None

    scripts = soup.find_all('script')
    brands_data = []
    found_data = False
    fieldnames = ['Marka', 'Urun Adedi']

    # Regex to find potential JSON objects ({...}) or arrays ([...])
    # This is a simplified pattern and might capture non-JSON, but is broader.
    # It looks for structures starting with { or [ and ending with } or ] respectively.
    # It tries to handle basic nesting but might fail on very complex structures.
    json_pattern = re.compile(r'(\{.*?\})|(\[.*?\])')
    # A potentially more robust (but complex) regex for nested structures:
    # json_pattern = re.compile(r'(\{((?:[^{}]|(?R))*)})|(\[((?:[^\[\]]|(?R))*)\])')


    st.write(f"Toplam {len(scripts)} script etiketi bulundu ve JSON yapıları aranıyor...")
    scripts_checked_for_json = 0
    json_structures_found = 0
    json_structures_parsed = 0

    for i, script in enumerate(scripts):
        script_content = script.get_text()
        if not script_content:
            continue

        scripts_checked_for_json += 1
        # Find *all* potential JSON-like strings within this script
        potential_jsons = json_pattern.finditer(script_content)
        found_json_in_this_script = False

        for match_obj in potential_jsons:
            # Get the matched string (either group 1 for {...} or group 2 for [...])
            json_like_string = match_obj.group(1) or match_obj.group(2)
            if not json_like_string: continue # Skip if match is empty

            json_structures_found += 1
            # st.text(f"Script #{i+1}: Potansiyel JSON bulundu: {json_like_string[:100]}...") # Debug

            # Attempt to parse this specific structure
            try:
                parsed_json = json.loads(json_like_string)
                json_structures_parsed += 1
                found_json_in_this_script = True # Mark that this script contained parseable JSON

                # Recursively search within the parsed JSON for the brand data
                brand_values = find_brands_in_json(parsed_json)

                if brand_values is not None:
                    st.success(f"Script #{i+1}: 'c_brand' yapısı JSON içinde bulundu!")
                    processed_count_in_script = 0
                    temp_brands_in_script = []
                    for item in brand_values:
                        if (isinstance(item, dict) and
                                'label' in item and isinstance(item['label'], str) and
                                'hitCount' in item and isinstance(item['hitCount'], int)):
                            temp_brands_in_script.append({
                                fieldnames[0]: item['label'],
                                fieldnames[1]: item['hitCount']
                            })
                            processed_count_in_script += 1

                    if processed_count_in_script > 0:
                       st.success(f"    -> {processed_count_in_script} geçerli marka/ürün sayısı bulundu ve eklendi.")
                       # Add unique brands to the main list
                       current_brand_labels = {d['Marka'] for d in brands_data}
                       new_brands_added = 0
                       for brand_entry in temp_brands_in_script:
                           if brand_entry['Marka'] not in current_brand_labels:
                               brands_data.append(brand_entry)
                               current_brand_labels.add(brand_entry['Marka'])
                               new_brands_added +=1
                       #if new_brands_added > 0: st.info(f"        -> {new_brands_added} yeni marka listeye eklendi.")
                       found_data = True
                       break # Exit the inner loop (potential_jsons) for this script

            except json.JSONDecodeError:
                # This is expected for many non-JSON strings captured by the broad regex
                # st.write(f"Script #{i+1}: Yakalanan '{json_like_string[:50]}...' JSON değil.") # Too verbose, disable
                pass
            except Exception as e:
                st.error(f"Script #{i+1} içindeki JSON benzeri yapı işlenirken hata: {e}")

        # If data found in this script's JSON structures, move to next script (or break outer loop if uncommented above)
        if found_data:
             break # Exit the main script loop once valid data is found and processed

    st.info(f"{scripts_checked_for_json} script kontrol edildi. Toplam {json_structures_found} JSON benzeri yapı bulundu, {json_structures_parsed} tanesi başarıyla ayrıştırıldı.")

    if not found_data:
        st.error("HTML içindeki script etiketlerinde aranan marka verisi yapısı bulunamadı.")
        st.warning("Olası Nedenler: \n - HTML dosyası beklenen veriyi içermiyor (farklı sayfa veya eksik kaynak).\n - Veri yapısı ('attributeId':'c_brand', 'values':[{'label':'...', 'hitCount':...}]) tamamen değişmiş.\n - Veri, JavaScript tarafından API çağrısıyla dinamik olarak yükleniyor olabilir (bu script ile çıkarılamaz).")
        return None, None

    st.info(f"Toplam {len(brands_data)} marka bulundu.")
    return brands_data, fieldnames

# --- Streamlit File Uploader ---
uploaded_file = st.file_uploader("HTML Dosyasını Buraya Sürükleyin veya Seçin", type=["html", "htm"])

if uploaded_file is not None:
    try:
        stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
        html_content = stringio.read()
        st.success(f"'{uploaded_file.name}' başarıyla yüklendi ve okundu.")

        with st.spinner("Marka verileri çıkarılıyor..."):
            # Use the new function
            brands_data, headers = extract_brands_from_scripts_aggressive_json(html_content)

        if brands_data and headers:
            st.success("Marka verileri başarıyla çıkarıldı!")
            df = pd.DataFrame(brands_data)
            df = df.sort_values(by='Marka').reset_index(drop=True)
            st.dataframe(df, use_container_width=True)
            csv_string = df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
               label="CSV Olarak İndir",
               data=csv_string,
               file_name='sephora_markalar.csv',
               mime='text/csv',
            )
        # Error/Warning messages are now handled within the extraction function

    except UnicodeDecodeError:
        st.error("Dosya kodlaması UTF-8 değil gibi görünüyor. Lütfen UTF-8 formatında kaydedilmiş bir HTML dosyası yükleyin.")
    except Exception as e:
        st.error(f"Dosya işlenirken genel bir hata oluştu: {e}")
        st.exception(e) # Log the full traceback
