import os, imaplib, email, json, re
# Modification ici pour éviter l'erreur d'import
import google.genai as genai 
from email.utils import parsedate_to_datetime
from email.header import decode_header

# Config Gemini 3 Flash avec la nouvelle syntaxe
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

def get_newsletter():
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(os.environ["EMAIL_USER"], os.environ["EMAIL_PASSWORD"])
    mail.select("inbox")
    
    # --- CONFIGURATION DES SOURCES ---
    AUTORISES = ["hugo@hugodecrypte.com", "hugodecrypte@kessel.media"]
    
    status, messages = mail.search(None, 'ALL')
    results = []
    
    ids = messages[0].split()
    for m_id in ids[-10:]:
        res, msg_data = mail.fetch(m_id, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        
        sender = str(msg.get("From")).lower()
        is_valide = any(addr.lower() in sender for addr in AUTORISES)
        
        if is_valide:
            dt = parsedate_to_datetime(msg.get("Date"))
            date_formattee = dt.strftime("%d %b")
            subject = decode_header(msg["Subject"])[0][0]
            if isinstance(subject, bytes): subject = subject.decode()
            
            html_body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        html_body = part.get_payload(decode=True).decode()
            else:
                html_body = msg.get_payload(decode=True).decode()
                
            if html_body:
                results.append({
                    "subject": subject, 
                    "html": html_body, 
                    "date": date_formattee,
                    "id_unique": f"{dt.strftime('%Y%m%d')}-{re.sub(r'[^a-zA-Z0-9]', '', subject[:10])}"
                })
    mail.logout()
    return results

newslettersFound = get_newsletter()

if newslettersFound:
    try:
        with open('manifest.json', 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except:
        manifest = []

    deja_presents = [item.get("titre_original", "") for item in manifest]
    themes_officiels = ["Politique", "Économie", "Technologie", "Écologie", "Société", "Culture", "Sport", "Géopolitique", "Science", "Insolite"]

    for nl in newslettersFound:
        if nl["subject"] in deja_presents:
            continue

        prompt = f"""Analyse cette newsletter. 
        1. Trouve l'URL de l'image principale. 
        2. Garde le HTML propre (gras, listes). 
        3. Thème parmi : {", ".join(themes_officiels)}.
        4. 10 questions QCM.
        Sortie JSON strict: {{"titre":"", "image":"", "theme":"", "contenu_html":"", "questions":[]}}"""
        
        try:
            response = client.models.generate_content(
                model='gemini-3-flash',
                contents=prompt + "\n\nTEXTE:\n" + nl['html']
            )
            
            match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                filename = f"quiz-{nl['id_unique']}.json"
                os.makedirs('data', exist_ok=True)
                with open(f"data/{filename}", 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False)
                
                manifest.append({
                    "date": nl['date'], 
                    "file": filename, 
                    "titre": data['titre'], 
                    "titre_original": nl['subject'],
                    "image": data.get('image', 'https://images.unsplash.com/photo-1504711434969-e33886168f5c'),
                    "theme": data['theme']
                })
        except Exception as e:
            print(f"Erreur : {e}")

    with open('manifest.json', 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False)
