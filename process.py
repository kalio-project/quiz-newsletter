import os, imaplib, email, json, re
from google import genai
from email.utils import parsedate_to_datetime
from email.header import decode_header

# 1. INITIALISATION DU CLIENT
# Il va chercher le secret 'GEMINI_API_KEY' que tu as créé dans GitHub
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

def get_newsletter():
    """Récupère les mails du compte quizz (EMAIL_USER)"""
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
            print(f"✅ MATCH : {subject[:35]}...")
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
                    "subject": subject, 
                    "html": html_body, 
                    "date": dt.strftime("%d %b"),
                    "id_unique": f"{dt.strftime('%Y%m%d')}-{re.sub(r'[^a-zA-Z0-9]', '', subject[:10])}"
                })
    mail.logout()
    return results

# --- GÉNÉRATION ---
newslettersFound = get_newsletter()

if newslettersFound:
    try:
        with open('manifest.json', 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except:
        manifest = []

    deja_presents = [item.get("titre_original", "") for item in manifest]
    
    # On teste les deux variantes de noms de modèles
    MODELES_A_TESTER = ['gemini-1.5-flash', 'models/gemini-1.5-flash']

    for nl in newslettersFound:
        if nl["subject"] in deja_presents:
            print(f"⏩ Déjà traité : {nl['subject']}")
            continue

        print(f"🤖 IA en cours pour : {nl['subject']}")
        
        prompt = f"""Analyse cette newsletter. 
        1. IMAGE : URL de l'image principale (src <img>).
        2. HTML : Garde seulement <b>, <i>, <ul>, <li>, <p>. 
        3. THÈME : Un seul mot (Politique, Sport, Économie, etc.). 
        4. QUIZ : 10 QCM (4 options, index correct, explication).
        Sortie JSON strict: {{"titre":"", "image":"", "theme":"", "contenu_html":"", "questions":[]}}"""
        
        success = False
        for m_name in MODELES_A_TESTER:
            if success: break
            try:
                # Appel direct sans forcer la version d'API
                response = client.models.generate_content(
                    model=m_name,
                    contents=prompt + "\n\nCONTENU :\n" + nl['html']
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
                    print(f"   💾 SUCCÈS ({m_name})")
                    success = True
            except Exception as e:
                print(f"   ❌ Échec avec {m_name}")

    with open('manifest.json', 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False)
    print("✅ Terminé !")
else:
    print("📢 Rien à traiter.")
