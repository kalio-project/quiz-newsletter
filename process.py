import os, imaplib, email, json, re
from google import genai
from email.utils import parsedate_to_datetime
from email.header import decode_header

# 1. CONFIGURATION ULTRA-SIMPLE
# On laisse la bibliothèque gérer les versions d'API toute seule
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

def get_newsletter():
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        mail.login(os.environ["EMAIL_USER"], os.environ["EMAIL_PASSWORD"])
    except Exception as e:
        print(f"❌ Erreur Gmail : {e}")
        return []

    mail.select("inbox")
    AUTORISES = ["hugodecrypte@kessel.media", "hugo@hugodecrypte.com", "qcm.newsletter@gmail.com"]
    
    status, messages = mail.search(None, 'ALL')
    results = []
    ids = messages[0].split()
    
    print(f"🔎 {len(ids)} mails trouvés.")

    for m_id in ids[-15:]:
        res, msg_data = mail.fetch(m_id, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        
        sender_raw = str(msg.get("From")).lower()
        sender = re.findall(r'[\w\.-]+@[\w\.-]+', sender_raw)
        sender = sender[0] if sender else sender_raw

        subject_parts = decode_header(msg["Subject"])
        subject = "".join([part.decode(enc or 'utf-8') if isinstance(part, bytes) else part for part, enc in subject_parts])

        if any(addr.lower() in sender for addr in AUTORISES):
            print(f"✅ NEWSLETTER : {subject[:30]}")
            dt = parsedate_to_datetime(msg.get("Date"))
            
            html_body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        html_body = part.get_payload(decode=True).decode(errors='ignore')
            else:
                html_body = msg.get_payload(decode=True).decode(errors='ignore')
                
            if html_body:
                results.append({
                    "subject": subject, "html": html_body, "date": dt.strftime("%d %b"),
                    "id_unique": f"{dt.strftime('%Y%m%d')}-{re.sub(r'[^a-zA-Z0-9]', '', subject[:10])}"
                })
    mail.logout()
    return results

newslettersFound = get_newsletter()

if newslettersFound:
    try:
        with open('manifest.json', 'r', encoding='utf-8') as f: manifest = json.load(f)
    except: manifest = []

    deja_presents = [item.get("titre_original", "") for item in manifest]

    for nl in newslettersFound:
        if nl["subject"] in deja_presents: continue

        print(f"🤖 IA en cours...")
        
        # CHANGEMENT DE NOM DE MODÈLE : On utilise le nom court sans prefixe
        try:
            response = client.models.generate_content(
                model='gemini-1.5-flash', 
                contents=f"Analyse cette newsletter et crée un quiz QCM. Sortie JSON strict: {{\"titre\":\"\", \"image\":\"\", \"theme\":\"\", \"contenu_html\":\"\", \"questions\":[]}}\n\nCONTENU :\n{nl['html']}"
            )
            
            match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                filename = f"quiz-{nl['id_unique']}.json"
                os.makedirs('data', exist_ok=True)
                with open(f"data/{filename}", 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False)
                
                manifest.append({
                    "date": nl['date'], "file": filename, "titre": data['titre'], 
                    "titre_original": nl['subject'], "image": data.get('image', ''), "theme": data['theme']
                })
                print(f"   💾 Sauvegardé !")
        except Exception as e:
            print(f"❌ Erreur IA : {e}")

    with open('manifest.json', 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False)
else:
    print("📢 Rien à traiter.")
