import os
import requests
import streamlit as st

# Sayfa Yapılandırması
st.set_page_config(
    page_title="AI Tabanlı Güvenli Ders İçeriği Platformu",
    page_icon="🎓",
    layout="wide"
)

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


def show_api_error(res):
    try:
        detail = res.json().get("detail", res.text)
    except Exception:
        detail = res.text
    st.error(f"Hata ({res.status_code}): {detail}")


def fetch_courses():
    try:
        res = requests.get(f"{API_BASE_URL}/courses", timeout=10)
        if res.status_code == 200:
            return res.json().get("courses", [])
    except Exception:
        pass
    return []


st.title("🎓 AI Tabanlı Güvenli Ders İçeriği Üretim Platformu")
st.markdown("---")

# Yan Menü (Sekmeler)
menu = st.sidebar.radio(
    "Menü",
    ["📚 PDF Yükle ve İşle (RAG)", "✨ Güvenli İçerik Üret", "🛡️ Güvenlik Denetim Günlüğü (Audit Logs)"]
)

# ----------------- 1. SEKME: PDF YÜKLEME -----------------
if menu == "📚 PDF Yükle ve İşle (RAG)":
    st.header("Ders Materyali Yükleme ve Güvenlik Taraması")
    st.info("Yüklenen PDF dosyası PII (Kişisel Veri) ve Prompt Injection filtrelerinden geçirilerek ChromaDB vektör tabanına indekslenir.")

    course_name = st.text_input("Ders Adı:", placeholder="Örn: Yapay Zeka")
    uploaded_file = st.file_uploader("Ders PDF Dosyasını Seçin", type=["pdf"])

    if st.button("Materyali Sisteme Yükle ve İndeksle", type="primary"):
        if not course_name or not uploaded_file:
            st.warning("Lütfen hem ders adını girin hem de bir PDF dosyası seçin.")
        else:
            with st.spinner("PDF okunuyor, güvenlik taramasından geçiriliyor ve indeksleniyor..."):
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
                data = {"course_name": course_name}

                try:
                    res = requests.post(f"{API_BASE_URL}/upload-course-pdf", data=data, files=files, timeout=180)
                    if res.status_code == 200:
                        result = res.json()
                        st.success("✅ Dosya başarıyla yüklendi ve indekslendi!")
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Toplam Sayfa", result.get("total_pages"))
                        col2.metric("Oluşturulan Parça (Chunk)", result.get("stored_chunks"))
                        col3.metric("Maskelenen PII", len(result.get("masked_pii_types", [])))
                        if result.get("masked_pii_types"):
                            st.warning(f"Algılanan ve Gizlenen Veriler: {', '.join(result.get('masked_pii_types'))}")
                    else:
                        show_api_error(res)
                except Exception as e:
                    st.error(f"Sunucuya bağlanılamadı: {e}")

# ----------------- 2. SEKME: İÇERİK ÜRETİMİ -----------------
elif menu == "✨ Güvenli İçerik Üret":
    st.header("RAG Destekli Güvenli İçerik Üretimi")

    courses = fetch_courses()
    if courses:
        st.caption("Yüklü dersler: " + ", ".join(courses))

    col1, col2 = st.columns(2)
    with col1:
        course_name = st.text_input("Ders Adı:", placeholder="Örn: Yapay Zeka")
        topic = st.text_input("Konu Başlığı:", placeholder="Örn: Geri Yayılım Algoritması")

    with col2:
        content_type = st.selectbox(
            "Üretim Formatı:",
            ["QUIZ", "LECTURE_NOTE", "SLIDE_OUTLINE"],
            format_func=lambda x: {
                "QUIZ": "Çoktan Seçmeli Sınav / Test (Quiz)",
                "LECTURE_NOTE": "Haftalık Ders Notu / Özet",
                "SLIDE_OUTLINE": "Sunum / Slayt Taslağı"
            }[x]
        )

    raw_instructions = st.text_area(
        "Özel Talimatlar / İstekler:",
        value="Yüklenen kaynak dokümana dayanarak 3 adet çoktan seçmeli soru ve açıklamalı cevap anahtarı hazırla.",
        max_chars=1500
    )

    if st.button("İçeriği Üret", type="primary"):
        if not course_name or not topic:
            st.warning("Lütfen ders adı ve konu alanlarını doldurun.")
        else:
            with st.spinner("İçerik güvenlik filtresinden geçiriliyor ve yapay zeka tarafından üretiliyor..."):
                payload = {
                    "course_name": course_name,
                    "topic": topic,
                    "content_type": content_type,
                    "raw_instructions": raw_instructions
                }
                try:
                    res = requests.post(f"{API_BASE_URL}/generate-content-with-rag", json=payload, timeout=120)
                    if res.status_code == 200:
                        st.session_state["gen_result"] = {"data": res.json(), "topic": topic}
                    else:
                        st.session_state.pop("gen_result", None)
                        show_api_error(res)
                except Exception as e:
                    st.error(f"API bağlantı hatası: {e}")

    # Sonuç session_state'te tutulur; indirme butonu sayfayı yenilese de içerik kaybolmaz
    result = st.session_state.get("gen_result")
    if result:
        data = result["data"]
        st.success("İçerik başarıyla üretildi!")

        sec = data.get("security_checks", {})
        pii = sec.get("masked_pii_types")
        st.markdown(f"""
        > **Güvenlik Doğrulaması:**  
        > - **Prompt Injection Filtresi:** {'Geçti ✅' if sec.get('prompt_injection_passed') else 'Engellendi ❌'}  
        > - **RAG Kaynağı Kullanımı:** {'Evet (Yüklenen PDF) 📄' if data.get('rag_context_used') else 'Genel Bilgi 🌐'}  
        > - **Maskelenen PII:** {', '.join(pii) if pii else 'Yok'}
        """)

        st.markdown("### 📝 Üretilen Akademik İçerik:")
        st.markdown(data.get("generated_content", ""))
        st.download_button(
            "⬇️ Markdown olarak indir",
            data=data.get("generated_content", ""),
            file_name="icerik.md",
            mime="text/markdown"
        )

# ----------------- 3. SEKME: AUDIT LOGS -----------------
elif menu == "🛡️ Güvenlik Denetim Günlüğü (Audit Logs)":
    st.header("Güvenlik ve İşlem Günlüğü (Audit Log)")
    st.markdown("Bu panelde sisteme yapılan saldırı girişimleri, maskelenen veriler ve üretim kayıtları listelenir. Erişim için yönetici anahtarı gerekir.")

    admin_key = st.text_input("Yönetici API Anahtarı:", type="password")

    if st.button("Kayıtları Getir / Yenile"):
        if not admin_key:
            st.warning("Lütfen yönetici anahtarını girin.")
        else:
            try:
                res = requests.get(
                    f"{API_BASE_URL}/security-audit-logs",
                    headers={"X-API-Key": admin_key},
                    timeout=15
                )
                if res.status_code == 200:
                    logs = res.json().get("logs", [])
                    if logs:
                        st.dataframe(logs, use_container_width=True)
                    else:
                        st.info("Henüz kayıt bulunmuyor.")
                else:
                    show_api_error(res)
            except Exception as e:
                st.error(f"Bağlantı hatası: {e}")