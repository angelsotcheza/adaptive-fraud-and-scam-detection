from flask import Flask, render_template, request, jsonify
import google.generativeai as genai
import os
import PyPDF2
from PIL import Image
import pytesseract
import json
import io

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

app = Flask(__name__)

# ---------------- GEMINI API ----------------
os.environ["GEMINI_API_KEY"] = "AIzaSyA360nZcBYOYtBRSAigakQq_fi8L4XvSIo"
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash-lite")

# ---------------- Verified Senders ----------------
VERIFIED_SENDERS = ["GCASH", "+639171234567", "PayPal", "BDO", "BPI", "PLDT", "Globe", "Smart"]

# ---------------- JSON extractor ----------------
def extract_json(text):
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except:
        return None

# ---------------- OCR ----------------
def extract_text_from_image(file):
    try:
        file.stream.seek(0)
        img = Image.open(io.BytesIO(file.read()))
        img = img.convert("L")
        text = pytesseract.image_to_string(img, config="--oem 3 --psm 6")
        return text.strip()
    except Exception as e:
        print("OCR Error:", e)
        return ""

# ---------------- File extraction ----------------
def extract_text_from_file(file):
    filename = file.filename.lower()
    if filename.endswith(".txt"):
        return file.read().decode("utf-8", errors="ignore")
    if filename.endswith(".pdf"):
        try:
            text = ""
            file.stream.seek(0)
            reader = PyPDF2.PdfReader(file.stream)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text.strip()
        except Exception as e:
            print("PDF Extraction Error:", e)
            return ""
    if filename.endswith((".jpg", ".jpeg", ".png")):
        extracted = extract_text_from_image(file)
        if extracted:
            return f"---IMAGE CONTENT---\n{extracted}\n---END---"
    return ""

# ---------------- Verified Sender Check ----------------
def contains_verified_sender(text):
    for sender in VERIFIED_SENDERS:
        if sender.lower() in text.lower():
            return True
    return False

# ---------------- GEMINI Text Analysis ----------------
def gemini_analyze_text(text):
    is_verified = contains_verified_sender(text)
    verified_note = "Verified Sender Detected." if is_verified else ""
    prompt = f"""
Respond ONLY in JSON:
{{
  "risk": "0-100",
  "classification": "Low Risk | Medium Risk | High Risk",
  "explanation": "short",
  "recommendations": ["short tip 1", "short tip 2"]
}}
Analyze message: {verified_note}
Content: {text}
"""
    try:
        response = model.generate_content(prompt)
        ai_text = getattr(response, "text", "")
        parsed = extract_json(ai_text)
        if parsed:
            # Ensure proper risk type
            risk = int(parsed.get("risk", 50))
            # Adjust classification to match risk
            if risk < 30:
                classification = "Low Risk"
            elif risk < 70:
                classification = "Medium Risk"
            else:
                classification = "High Risk"

            # Override classification if verified sender
            if is_verified and risk < 30:
                classification = "Low Risk"
                explanation = parsed.get("explanation", "Analysis indicates potential risk.") + " Verified sender detected; content appears safe."
            else:
                explanation = parsed.get("explanation", "Analysis indicates potential risk.")

            recommendations = parsed.get("recommendations", ["Be cautious."])

            return {
                "risk": risk,
                "classification": classification,
                "explanation": explanation,
                "recommendations": recommendations,
                "input_text": text
            }

        return {
            "risk": 50,
            "classification": "Medium Risk",
            "explanation": "Unable to parse AI response.",
            "recommendations": ["Try again."],
            "input_text": text
        }
    except Exception as e:
        print("Gemini Analyze Error:", e)
        return {
            "risk": 50,
            "classification": "Medium Risk",
            "explanation": "Error analyzing the content.",
            "recommendations": ["Try again later."],
            "input_text": text
        }

# ---------------- GEMINI URL Analysis ----------------
def gemini_url_analyze(url):
    prompt = f"""
JSON only:
{{
 "risk": "0-100",
 "classification": "Low Risk | Medium Risk | High Risk",
 "explanation": "short",
 "recommendations": ["short tip"]
}}
Analyze URL: {url}
"""
    try:
        response = model.generate_content(prompt)
        text = getattr(response, "text", "")
        parsed = extract_json(text)
        if parsed:
            risk = int(parsed.get("risk", 50))
            if risk < 30:
                classification = "Low Risk"
            elif risk < 70:
                classification = "Medium Risk"
            else:
                classification = "High Risk"

            return {
                "risk": risk,
                "classification": classification,
                "explanation": parsed.get("explanation", "URL analyzed."),
                "recommendations": parsed.get("recommendations", ["Be cautious."]),
                "input_url": url
            }
        return {
            "risk":50,
            "classification":"Medium Risk",
            "explanation":"Unable to analyze URL.",
            "recommendations":["Be cautious."],
            "input_url": url
        }
    except Exception as e:
        print("Gemini URL Analyze Error:", e)
        return {
            "risk":50,
            "classification":"Medium Risk",
            "explanation":"URL analysis error.",
            "recommendations":["Try again later."],
            "input_url": url
        }

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/analyze_text", methods=["POST"])
def analyze_text_route():
    text = request.form.get("text_input", "").strip()
    file = request.files.get("file")
    combined = text
    if file:
        extracted = extract_text_from_file(file)
        if extracted:
            combined += "\n" + extracted
    if not combined.strip():
        return jsonify({
            "risk": 50,
            "classification": "Medium Risk",
            "explanation": "No readable input.",
            "recommendations": ["Provide text or a clear image."],
            "input_text": ""
        })
    result = gemini_analyze_text(combined)
    return jsonify(result)

@app.route("/analyze_url", methods=["POST"])
def analyze_url_route():
    url = request.form.get("url_input", "").strip()
    if not url:
        return jsonify({
            "risk": 50,
            "classification": "Medium Risk",
            "explanation": "No URL provided.",
            "recommendations": ["Enter a valid URL."],
            "input_url": ""
        })
    result = gemini_url_analyze(url)
    return jsonify(result)

# ---------------- MAIN ----------------
if __name__ == "__main__":
    app.run(debug=True)
