import os, imaplib, email, json, re
from google import genai
from email.utils import parsedate_to_datetime
from email.header import decode_header

# 1. CONFIGURATION DU CLIENT GEMINI
# Utilisation du modèle flash-latest pour éviter les erreurs 404
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

def get_newsletter():
    """Récupère les newsletters depuis Gmail"""
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        mail.login(os.environ["EMAIL_USER"], os.environ["EMAIL_PASSWORD"])
    except Exception as e:
        print(f"❌ Erreur Connexion Gmail : {e}")
        return []

    mail.select("inbox")
    
    # Adresses autorisées
    AUTORISES = [
        "hugodecrypte@kessel.media", 
        "hugo@hugodecrypte.com", 
        "qcm.newsletter@gmail.com"
    ]
    
    status, messages = mail.search(None, 'ALL')
    results = []
    ids = messages[0].split()
    
    print(f"🔎 {len(ids)} mails en boîte. Analyse des 15 derniers...")

    for m_id in ids[-15:]:
        res, msg_data = mail.fetch(m_id, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        
        # Extraction de l'expéditeur
        sender_raw = str(msg.get("From")).lower()
        sender_email = re.findall(r'[\w\.-]+@[\w\.-]+', sender_raw)
        sender = sender_email[0] if sender_email else sender_raw

        # Décodage du sujet
        subject_parts = decode_header(msg["Subject"])
        subject = ""
        for part, encoding in subject_parts:
            if isinstance(part, bytes):
                subject += part.decode(encoding or "utf-8", errors="ignore")
            else:
                subject += part

        # Filtrage
        if any(addr.lower() in sender for addr in AUTORISES):
            print(f"✅ NEWSLETTER TROUVÉE : {subject[:40]}")
            dt = parsedate_to_datetime(msg.get("Date"))
            
            html_body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        html_body = part.get_payload(decode=True).decode(errors='ignore')
            else:
                html_body = msg.get_payload(decode=True).decode(errors='ignore')
                
            if html_body:
                # ID unique pour éviter les doublons
                id_propre = re.sub(r'[^a-zA-Z0-9]', '', subject[:10])
                results.append({
                    "subject": subject, 
                    "html": html_body, 
                    "date": dt.strftime("%d %b"),
                    "id_unique": f"{dt.strftime('%Y%m%d')}-{id_propre}"
                })
        else:
            print(f"   ❌ Ignoré : {sender}")

    mail.logout()
    return results

# --- TRAITEMENT IA ---
newslettersFound = get_newsletter()

if newslettersFound:
    try:
        with open('manifest.json', 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except:
        manifest = []

    deja_presents = [item.get("titre_original", "") for item in manifest]
    themes_dispo = ["Politique", "Économie", "Technologie", "Écologie", "Société", "Culture", "Sport", "Géopolitique", "Science", "Insolite"]

    for nl in newslettersFound:
        if nl["subject"] in deja_presents:
            print(f"⏩ Déjà dans le manifest : {nl['subject']}")
            continue

        print(f"🤖 IA en cours (Modèle: gemini-1.5-flash-latest)...")
        
        prompt = f"""Analyse cette newsletter et crée un quiz.
        1. IMAGE : Trouve l'URL de l'image de couverture (src <img>).
        2. HTML : Garde seulement <b>, <i>, <ul>, <li>, <p>. Retire les pubs.
        3. THÈME : Choisis parmi : {", ".join(themes_dispo)}.
        4. QUIZ : 10 questions QCM (4 options, index correct 0-3, explication).
        
        RÉPONSE EN JSON STRICT UNIQUEMENT :
        {{
            "titre": "Titre",
            "image": "URL",
            "theme": "Thème",
            "contenu_html": "HTML",
            "questions": [{{"q":"?","options":["","","",""],"correct":0,"explication":""}}]
        }}"""
        
        try:
            # Utilisation du nom de modèle complet et stable
            response = client.models.generate_content(
                model='gemini-1.5-flash-latest',
                contents=prompt + "\n\nCONTENU :\n" + nl['html']
            )
            
            # Extraction du JSON
            match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                
                # Sauvegarde du fichier Quiz
                filename = f"quiz-{nl['id_unique']}.json"
                os.makedirs('data', exist_ok=True)
                with open(f"data/{filename}", 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False)
                
                # Mise à jour Manifest
                manifest.append({
                    "date": nl['date'], 
                    "file": filename, 
                    "titre": data['titre'], 
                    "titre_original": nl['subject'],
                    "image": data.get('image', 'https://images.unsplash.com/photo-1504711434969-e33886168f5c'),
                    "theme": data['theme']
                })
                print(f"   💾 Sauvegardé : {filename}")
        except Exception as e:
            print(f"❌ Erreur Gemini : {e}")

    # Écriture finale
    with open('manifest.json', 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False)
    print("✅ Terminé !")

else:
    print("📢 Rien à traiter.")
