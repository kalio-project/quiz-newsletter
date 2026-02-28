import os, imaplib, email, json, re, time
from google import genai
from bs4 import BeautifulSoup
from datetime import datetime
from email.header import decode_header

# --- CONFIGURATION ---
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
SOURCE_FOLDER = "newsletters_html"
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

def clean_html_for_ia(raw_html):
    soup = BeautifulSoup(raw_html, 'html.parser')
    for tag in soup(["script", "style"]): tag.decompose()
    return ' '.join(soup.get_text(separator=' ').split())

def fetch_emails():
    if not EMAIL_USER or not EMAIL_PASSWORD:
        print("⚠️ Identifiants Gmail manquants.")
        return []
    newsletters = []
    try:
        print(f"📧 Connexion à Gmail...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASSWORD)
        mail.select("HUGO")
        status, messages = mail.search(None, 'UNSEEN')
        if status != "OK" or not messages[0]:
            print("✅ Aucun nouveau mail.")
            mail.logout()
            return []
        for m_id in messages[0].split():
            res, data = mail.fetch(m_id, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            subj = decode_header(msg["Subject"])[0][0]
            if isinstance(subj, bytes): subj = subj.decode(errors='ignore')
            body_html = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        body_html = part.get_payload(decode=True).decode(errors='ignore')
            else:
                body_html = msg.get_payload(decode=True).decode(errors='ignore')
            if body_html:
                newsletters.append({"id": f"mail-{m_id.decode()}", "html": body_html, "title": subj})
        mail.logout()
    except Exception as e: print(f"❌ Gmail Error: {e}")
    return newsletters

def run():
    if not os.path.exists('data'): os.makedirs('data')
    try:
        with open('manifest.json', 'r', encoding='utf-8') as f: manifest = json.load(f)
    except: manifest = []
    
    deja_vus = [m.get("titre_original") for m in manifest]
    sources = fetch_emails()
    
    if os.path.exists(SOURCE_FOLDER):
        for f in os.listdir(SOURCE_FOLDER):
            if f.lower().endswith(('.htm', '.html')) and f not in deja_vus:
                with open(os.path.join(SOURCE_FOLDER, f), 'r', encoding='utf-8') as file:
                    sources.append({"id": f, "html": file.read(), "title": f})

    if not sources: return
    item = sources[0]
    if item["id"] in deja_vus: return

    print(f"🤖 Analyse de : {item['title']}")
    texte_ia = clean_html_for_ia(item["html"])
    prompt = "Génère un quiz JSON de 10 questions. Format: {\"theme_global\": \"\", \"titre\": \"\", \"questions\": [{\"q\": \"\", \"options\": [\"\", \"\", \"\", \"\"], \"correct\": 0, \"explication\": \"\"}]}"

    # --- TENTATIVE AVEC RETRY ---
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model='gemini-1.5-flash', 
                contents=f"{prompt}\n\nTexte: {texte_ia}"
            )
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                quiz_data = json.loads(json_match.group())
                quiz_data['html_affichage'] = item["html"]
                quiz_id = datetime.now().strftime("%Y%m%d-%H%M")
                dest_path = f"data/quiz-{quiz_id}.json"
                with open(dest_path, 'w', encoding='utf-8') as f:
                    json.dump(quiz_data, f, ensure_ascii=False, indent=2)
                manifest.append({
                    "date": datetime.now().strftime("%d %b %Y"),
                    "file": dest_path,
                    "titre": quiz_data.get('titre', item['title']),
                    "titre_original": item["id"],
                    "theme": quiz_data.get('theme_global', 'ACTU')
                })
                with open('manifest.json', 'w', encoding='utf-8') as f:
                    json.dump(manifest, f, ensure_ascii=False, indent=2)
                print(f"✅ Quiz créé !")
                return # Succès, on sort de la boucle
        except Exception as e:
            print(f"⚠️ Essai {attempt+1} échoué : {e}")
            if attempt == 0: 
                print("Attente de 10s...")
                time.sleep(10)

if __name__ == "__main__":
    run()
