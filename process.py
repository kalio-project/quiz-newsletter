import os, imaplib, email, json, re
from google import genai
from email.utils import parsedate_to_datetime
from email.header import decode_header

# 1. CONNEXION À L'IA (MODÈLE 2.5 FLASH DÉTECTÉ)
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
    # Liste des expéditeurs autorisés
    AUTORISES = ["hugodecrypte@kessel.media", "hugo@hugodecrypte.com", "qcm.newsletter@gmail.com"]
    
    status, messages = mail.search(None, 'ALL')
    results = []
    ids = messages[0].split()
    
    print(f"🔎 {len(ids)} mails en boîte. Analyse des 15 derniers...")

    for m_id in ids[-15:]:
        res, msg_data = mail.fetch(m_id, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        
        # Nettoyage expéditeur
        sender_raw = str(msg.get("From")).lower()
        sender = re.findall(r'[\w\.-]+@[\w\.-]+', sender_raw)
        sender = sender[0] if sender else sender_raw

        # Décodage du sujet
        subject_parts = decode_header(msg["Subject"])
        subject = "".join([part.decode(enc or 'utf-8') if isinstance(part, bytes) else part for part, enc in subject_parts])

        if any(addr.lower() in sender for addr in AUTORISES):
            print(f"✅ NEWSLETTER TROUVÉE : {subject[:40]}")
            dt = parsedate_to_datetime(msg.get("Date"))
            
            # Extraction du contenu HTML
            html_body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        html_body = part.get_payload(decode=True).decode(errors='ignore')
            else:
                html_body = msg.get_payload(decode=True).decode(errors='ignore')
                
            if html_body:
                id_propre = re.sub(r'[^a-zA-Z0-9]', '', subject[:10])
                results.append({
                    "subject": subject, 
                    "html": html_body, 
                    "date": dt.strftime("%d %b"),
                    "id_unique": f"{dt.strftime('%Y%m%d')}-{id_propre}"
                })
    mail.logout()
    return results

# --- TRAITEMENT PRINCIPAL ---
newslettersFound = get_newsletter()

if newslettersFound:
    try:
        with open('manifest.json', 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except:
        manifest = []

    deja_presents = [item.get("titre_original", "") for item in manifest]
    
    # Utilisation du modèle gemini-2.5-flash qui est celui qui fonctionne sur ta clé
    MODEL_NAME = 'gemini-2.5-flash'

    for nl in newslettersFound:
        if nl["subject"] in deja_presents:
            print(f"⏩ Déjà traité : {nl['subject']}")
            continue

        print(f"🤖 IA en cours (Modèle: {MODEL_NAME})...")
        
        prompt = f"""Tu es un expert média. Analyse cette newsletter et crée un quiz.
        1. IMAGE : URL de l'image principale (src de la balise <img>).
        2. HTML : Garde seulement <b>, <i>, <ul>, <li>, <p>. Retire les pubs.
        3. THÈME : Choisis parmi : Politique, Économie, Technologie, Écologie, Société, Culture, Sport, Géopolitique, Science, Insolite.
        4. QUIZ : 10 QCM (4 options, index correct 0-3, explication).
        
        RÉPONSE EN JSON STRICT UNIQUEMENT :
        {{
            "titre": "Titre accrocheur",
            "image": "URL de l'image",
            "theme": "Thème choisi",
            "contenu_html": "HTML nettoyé",
            "questions": [
                {{"q": "Ma question ?", "options": ["A", "B", "C", "D"], "correct": 0, "explication": "Pourquoi..."}}
            ]
        }}"""
        
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt + "\n\nCONTENU DE LA NEWSLETTER :\n" + nl['html']
            )
            
            # Extraction du JSON dans la réponse
            match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                
                # Sauvegarde du fichier Quiz
                filename = f"quiz-{nl['id_unique']}.json"
                os.makedirs('data', exist_ok=True)
                with open(f"data/{filename}", 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False)
                
                # Mise à jour du Manifest
                manifest.append({
                    "date": nl['date'], 
                    "file": filename, 
                    "titre": data['titre'], 
                    "titre_original": nl['subject'],
                    "image": data.get('image', 'https://images.unsplash.com/photo-1504711434969-e33886168f5c'),
                    "theme": data['theme']
                })
                print(f"   💾 Fichier créé : {filename}")
        except Exception as e:
            print(f"❌ Erreur IA : {e}")

    # Enregistrement final du manifest
    with open('manifest.json', 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False)
    print("✅ Terminé !")

else:
    print("📢 Rien à traiter aujourd'hui.")
