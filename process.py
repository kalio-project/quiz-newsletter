import os, imaplib, email, json, re, html, time
from google import genai
from email.utils import parsedate_to_datetime
from email.header import decode_header

# --- CONFIGURATION ---
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
THEMES_LIST = "POLITIQUE, GÉOPOLITIQUE, ÉCONOMIE, SOCIÉTÉ, SANTÉ, ENVIRONNEMENT, TECHNOLOGIE, CULTURE, SPORT, INTERNATIONAL"

def clean_newsletter_html(raw_html):
    start_marker = r"Ouvrir\s+dans\s+le\s+navigateur"
    end_marker = r"Vous\s+avez\s+aim\u00e9\s+cette\s+newsletter"
    content = raw_html
    split_start = re.split(start_marker, content, flags=re.IGNORECASE)
    if len(split_start) > 1: content = split_start[-1]
    split_end = re.split(end_marker, content, flags=re.IGNORECASE)
    if len(split_end) > 1: content = split_end[0]
    content = re.sub(r'^.*?<body.*?>', '', content, flags=re.DOTALL | re.IGNORECASE)
    return content.strip()

def get_newsletters():
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        mail.login(os.environ["EMAIL_USER"], os.environ["EMAIL_PASSWORD"])
    except Exception as e:
        print(f"Erreur connexion Gmail : {e}")
        return []

    status, select_info = mail.select("HUGO")
    if status != 'OK':
        print("❌ Libellé 'HUGO' introuvable.")
        mail.logout()
        return []

    status, messages = mail.search(None, 'ALL')
    ids = messages[0].split()
    
    if not ids:
        print("📁 Le dossier 'HUGO' est vide.")
        mail.logout()
        return []

    AUTORISES = ["hugodecrypte@kessel.media", "hugo@hugodecrypte.com", "qcm.newsletter@gmail.com"]
    results = []
    # On prend les 10 derniers
    for m_id in ids[-10:]:
        res, data = mail.fetch(m_id, "(RFC822)")
        msg = email.message_from_bytes(data[0][1])
        sender = str(msg.get("From", "")).lower()
        if any(addr.lower() in sender for addr in AUTORISES):
            subject_parts = decode_header(msg["Subject"])
            subject = "".join([part.decode(enc or 'utf-8') if isinstance(part, bytes) else part for part, enc in subject_parts])
            dt = parsedate_to_datetime(msg.get("Date"))
            body_html = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        body_html = part.get_payload(decode=True).decode(errors='ignore')
            else:
                body_html = msg.get_payload(decode=True).decode(errors='ignore')
            
            if body_html:
                text_clean = re.sub(r'<(style|script|head).*?>.*?</\1>', '', body_html, flags=re.DOTALL | re.IGNORECASE)
                text_clean = re.sub(r'<.*?>', ' ', text_clean)
                results.append({
                    "subject": subject, "full_html": clean_newsletter_html(body_html),
                    "text_only": html.unescape(text_clean), "date": dt.strftime("%d %b %Y"),
                    "id": f"{dt.strftime('%Y%m%d')}-{re.sub(r'[^a-z]', '', subject.lower())[:10]}"
                })
    mail.logout()
    return results

# --- EXÉCUTION ---
newsletters = get_newsletters()

if newsletters:
    try:
        with open('manifest.json', 'r', encoding='utf-8') as f: manifest = json.load(f)
    except: manifest = []
    
    deja_vus = [m.get("titre_original") for m in manifest]

    for nl in newsletters:
        if nl["subject"] in deja_vus:
            print(f"⏩ Déjà fait : {nl['subject']}")
            continue

        # PETITE PAUSE AVANT DE COMMENCER POUR LE QUOTA
        print("⏳ Attente de 15s (quota safety)...")
        time.sleep(15)

        print(f"🤖 Analyse IA : {nl['subject']}...")
        prompt = f"""Génère un JSON STRICT (10 questions). Thèmes autorisés : [{THEMES_LIST}].
        Chaque question doit avoir son champ 'theme' parmi cette liste.
        Structure : {{"theme_global": "", "titre": "", "questions": [{{"q": "", "options": [], "correct": 0, "explication": "", "theme": ""}}]}}"""

        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=f"{prompt}\n\nTEXTE :\n{nl['text_only'][:8000]}"
            )
            
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                quiz_data = json.loads(json_match.group())
                quiz_data['contenu_html'] = nl['full_html']
                
                img_url = "https://images.unsplash.com/photo-1504711434969-e33886168f5c"
                img_candidates = re.findall(r'src="(https://.*?)"', nl['full_html'])
                for url in img_candidates:
                    if any(x in url for x in ["kessel", "usercontent", "googleusercontent"]):
                        img_url = url
                        break
                
                quiz_filename = f"data/quiz-{nl['id']}.json"
                os.makedirs('data', exist_ok=True)
                with open(quiz_filename, 'w', encoding='utf-8') as f:
                    json.dump(quiz_data, f, ensure_ascii=False)
                
                manifest.append({
                    "date": nl['date'], "file": quiz_filename, "titre": quiz_data.get('titre', nl['subject']),
                    "titre_original": nl['subject'], "image": img_url, "theme": quiz_data.get('theme_global', 'INTERNATIONAL')
                })
                
                with open('manifest.json', 'w', encoding='utf-8') as f:
                    json.dump(manifest, f, ensure_ascii=False, indent=2)
                
                print(f"✅ Créé avec succès.")
                
        except Exception as e:
            if "429" in str(e):
                print("⚠️ Quota épuisé. Fin du run actuel.")
                break
            else:
                print(f"❌ Erreur : {e}")
else:
    print("Aucun mail trouvé.")
