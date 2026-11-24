import os
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from dotenv import load_dotenv
import google.generativeai as genai

from core.security import check_prompt_injection, mask_pii_data
from core.database import init_db, log_event, get_all_logs
from services.pdf_service import extract_and_sanitize_pdf
from services.rag_service import save_document_to_vector_db, query_relevant_context

load_dotenv()

# Veritabanini baslat
init_db()

api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

app = FastAPI(
    title="AI Tabanli Guvenli Ders Icerigi Platformu",
    description="RAG ve Guvenlik Katmanli Akademik Icerik Uretim API",
    version="2.1.0"
)

def get_gemini_model():
    for m in genai.list_models():
        if "generateContent" in m.supported_generation_methods:
            return genai.GenerativeModel(m.name)
    raise Exception("generateContent destekleyen model bulunamadi.")

# --- 1. PDF YUKLEME ---
@app.post("/upload-course-pdf")
async def upload_course_pdf(
    course_name: str = Form(...),
    file: UploadFile = File(...)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Sadece PDF dosyasi yukleyebilirsiniz.")

    file_bytes = await file.read()
    pdf_data = extract_and_sanitize_pdf(file_bytes)

    if pdf_data["has_injection"]:
        log_event("SECURITY_ALERT", course_name, file.filename, "BLOCKED", f"Zararli PDF: {pdf_data['injection_message']}")
        raise HTTPException(status_code=400, detail=f"PDF iceriginde zararli komut saptandi: {pdf_data['injection_message']}")

    chunks_count = save_document_to_vector_db(course_name, file.filename, pdf_data["clean_text"])
    
    log_event("PDF_UPLOAD", course_name, file.filename, "SUCCESS", f"Sayfa: {pdf_data['total_pages']}, Maskelenen PII: {pdf_data['masked_pii']}, Parca: {chunks_count}")

    return {
        "status": "SUCCESS",
        "file_name": file.filename,
        "course_name": course_name,
        "total_pages": pdf_data["total_pages"],
        "masked_pii_types": pdf_data["masked_pii"],
        "stored_chunks": chunks_count
    }

# --- 2. RAG TABANLI ICERIK URETME ---
class RAGContentRequest(BaseModel):
    course_name: str
    topic: str
    content_type: str
    raw_instructions: str

@app.post("/generate-content-with-rag")
def generate_content_with_rag(req: RAGContentRequest):
    # Prompt injection denetimi
    is_inj, msg = check_prompt_injection(req.raw_instructions)
    if is_inj:
        log_event("SECURITY_ALERT", req.course_name, req.topic, "BLOCKED", f"Prompt Injection Tespit Edildi: {msg}")
        raise HTTPException(status_code=400, detail=msg)

    clean_inst, masked_pii = mask_pii_data(req.raw_instructions)
    context = query_relevant_context(req.course_name, req.topic)

    system_prompt = f"""
    Sen guvenli bir akademik icerik uretim asistanisin.
    Ders: {req.course_name}
    Konu: {req.topic}
    Istenen Format: {req.content_type}
    
    YUKLENEN DOKUMAN KAYNAK METNI (Sadece buradaki bilgilere sadik kal, uydurma):
    {context if context else "Bu ders icin ozel kaynak bulunamadi, genel akademik mufredata gore uret."}
    
    Guvenlik Kurallari:
    - Sadece egitim ve akademik amacli icerik uret.
    - Telif hakki veya etik disi ifadelere izin verme.
    
    Talimat:
    {clean_inst}
    """

    try:
        model = get_gemini_model()
        response = model.generate_content(system_prompt)
        ai_output = response.text
        
        log_event("CONTENT_GEN", req.course_name, req.topic, "SUCCESS", f"Format: {req.content_type}, RAG: {bool(context)}, PII: {masked_pii}")
    except Exception as e:
        log_event("CONTENT_GEN", req.course_name, req.topic, "FAILED", f"AI Calisma Hatasi: {str(e)}")
        raise HTTPException(status_code=500, detail=f"AI Hatasi: {str(e)}")

    return {
        "status": "SUCCESS",
        "content_type": req.content_type,
        "rag_context_used": bool(context),
        "security_checks": {
            "prompt_injection_passed": True,
            "masked_pii_types": masked_pii
        },
        "generated_content": ai_output
    }

# --- 3. AUDIT LOGLARI GORUNTULEME ENDPOINT'I ---
@app.get("/security-audit-logs")
def get_security_audit_logs():
    return {
        "status": "SUCCESS",
        "total_records": len(get_all_logs()),
        "logs": get_all_logs()
    }