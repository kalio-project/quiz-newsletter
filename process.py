import os, imaplib, email, json, re
import google.generativeai as genai
from email.header import decode_header

# Config IA
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-flash')

def get_newsletter():
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(os.environ["EMAIL_USER"], os.environ["EMAIL_PASSWORD"])
    mail.select("inbox")
    # On cherche uniquement les mails non lus
    status, messages = mail.search(None, 'UNSEEN')
    results = []
    for m_id in messages[0].split()[-3:]:
        res, msg = mail.fetch(m_id, "(RFC822)")
        msg = email.message_from_bytes(msg[0][1])
        subject = decode_header(msg["Subject"])[0][0]
        if isinstance(subject, bytes): subject = subject.decode()
        
        html_body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    html_body = part.get_payload(decode=True).decode()
        else:
            html_body = msg.get_payload(decode=True).decode()
        results.append({"subject": subject, "html": html_body, "sender": msg.get("From")})
    return results

# Exécution
newsletters = get_newsletter()
if newsletters:
    try:
        with open('manifest.json', 'r') as f: manifest = json.load(f)
    except: manifest = []

    themes_officiels = ["Politique", "Économie", "Technologie", "Écologie", "Société", "Culture", "Sport", "Géopolitique", "Science", "Insolite"]

    for nl in newsletters:
        source = "HugoDécrypte" if "hugo" in nl['sender'].lower() else "Newsletter"
        
        prompt = f"""Analyse cette newsletter. 
        1. Trouve l'URL de l'image de couverture principale (balise <img>). 
        2. Garde la mise en forme HTML (gras, listes) sans les pubs. 
        3. Choisis le thème le plus proche parmi : {", ".join(themes_officiels)}.
        4. Génère 10 questions QCM (4 options, 1 correct, 1 explication).
        Sortie JSON strict: {{"titre":"", "image":"", "theme":"", "contenu_html":"", "questions":[]}}"""
        
        response = model.generate_content(prompt + "\n\nTEXTE:\n" + nl['html'])
        # Extraction du JSON dans la réponse
        match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            filename = f"quiz-{len(manifest)}.json"
            os.makedirs('data', exist_ok=True)
            with open(f"data/{filename}", 'w') as f: json.dump(data, f)
            
            manifest.append({
                "date": "28 Fév", 
                "file": filename, 
                "titre": data['titre'], 
                "image": data.get('image', 'https://images.unsplash.com/photo-1504711434969-e33886168f5c'),
                "theme": data['theme']
            })

    with open('manifest.json', 'w') as f: json.dump(manifest, f)
