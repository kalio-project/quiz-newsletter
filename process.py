import os, imaplib, email, json, re
import google.genai as genai 
from email.utils import parsedate_to_datetime
from email.header import decode_header

# Configuration Gemini 3 Flash
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

def get_newsletter():
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        mail.login(os.environ["EMAIL_USER"], os.environ["EMAIL_PASSWORD"])
    except Exception as e:
        print(f"❌ Erreur Connexion Gmail : {e}")
        return []

    mail.select("inbox")
    
    # --- TA LISTE D'EXPÉDITEURS ---
    # J'ai ajouté ton adresse exacte ici
    AUTORISES = [
        "hugodecrypte@kessel.media", 
        "hugo@hugodecrypte.com", 
        "qcm.newsletter@gmail.com"
    ]
    
    status, messages = mail.search(None, 'ALL')
    results = []
    
    ids = messages[0].split()
    print(f"🔎 {len(ids)} mails trouvés dans la boîte. Analyse des 15 derniers...")

    for m_id in ids[-15:]:
        res, msg_data = mail.fetch(m_id, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        
        # Nettoyage de l'expéditeur (ex: "Hugo <hugo@mail.com>" -> "hugo@mail.com")
        sender_raw = str(msg.get("From")).lower()
        sender_email = re.findall(r'[\w\.-]+@[\w\.-]+', sender_raw)
        sender = sender_email[0] if sender_email else sender_raw

        subject = decode_header(msg["Subject"])[0][0]
        if isinstance(subject, bytes): subject = subject.decode()

        print(f"--- Analyse : {subject[:30]}... | De : {sender}")

        is_valide = any(addr.lower() in sender for addr in AUTORISES)
        
        if is_valide:
            print(f"   ✅ MATCH ! Cet expéditeur est autorisé.")
            dt = parsedate_to_datetime(msg.get("Date"))
            date_formattee = dt.strftime("%d %b")
            
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
        else:
            print(f"   ❌ Ignoré (Expéditeur non listé)")

    mail.logout()
    return results

# --- LOGIQUE DE GÉNÉRATION ---
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
            print(f"⏩ Déjà dans le manifest : {nl['subject']}")
            continue

        prompt = f"""Analyse cette newsletter. 
        1. Trouve l'URL de l'image de couverture principale. 
        2. Garde le HTML propre (gras, listes). 
        3. Choisis le thème parmi : {", ".join(themes_officiels)}.
        4. Génère 10 questions QCM.
        Sortie JSON strict: {{"titre":"", "image":"", "theme":"", "contenu_html":"", "questions":[]}}"""
        
        try:
            print(f"🤖 IA en cours pour : {nl['subject']}")
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
                print(f"   💾 Quiz sauvegardé : {filename}")
        except Exception as e:
            print(f"❌ Erreur Gemini : {e}")

    with open('manifest.json', 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False)
else:
    print("📢 Fin du scan : Aucun nouveau mail valide détecté.")
