import os, imaplib, email, json, re, html, requests
from google import genai
from email.utils import parsedate_to_datetime
from datetime import datetime

# --- CONFIGURATION ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS") 

client = genai.Client(api_key=GEMINI_KEY)

def download_image(url, file_id):
    if not os.path.exists('images'): os.makedirs('images')
    path = f"images/vignette-{file_id}.jpg"
    if os.path.exists(path): return path
    try:
        res = requests.get(url.replace('&amp;', '&'), timeout=10)
        if res.status_code == 200:
            with open(path, 'wb') as f: f.write(res.content)
            return path
    except: pass
    return "https://via.placeholder.com/600x400?text=ActuQuiz"

def clean_html_content(raw_html):
    # Coupe le haut technique
    if "Ouvrir dans le navigateur" in raw_html:
        raw_html = raw_html.split("Ouvrir dans le navigateur")[-1]
    
    # Coupe la fin (pub/parrainage)
    fin_nl = ["Vous avez aimé cette newsletter ?", "Cette édition vous a plu ?", "Partager cette édition"]
    for phrase in fin_nl:
        if phrase in raw_html:
            raw_html = raw_html.split(phrase)[0]
            break

    # Nettoyage anti-blanc (SVG, Styles, Preheaders)
    raw_html = re.sub(r'<style[^>]*>.*?</style>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
    raw_html = re.sub(r'<svg[^>]*>.*?</svg>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
    raw_html = re.sub(r'<div[^>]*class="preheader"[^>]*>.*?</div>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
    return raw_html.strip()

def process_emails():
    print("Connexion IMAP...")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(EMAIL_USER, EMAIL_PASS)
    
    # --- MODIFICATION : SÉLECTION DU DOSSIER HUGO ---
    # Si le dossier est un sous-dossier, le nom peut être "HUGO" ou "Label/HUGO"
    status, count = mail.select("HUGO")
    if status != 'OK':
        print("Erreur : Le dossier 'HUGO' est introuvable. Vérifie le nom exact (Majuscules/Minuscules).")
        return

    # Recherche l'adresse spécifique
    status, messages = mail.search(None, '(FROM "hugodecrypte@kessel.media")')
    email_ids = messages[0].split()

    manifest = []
    if os.path.exists('manifest.json'):
        with open('manifest.json', 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    
    deja_vus = [m.get('titre_original') for m in manifest]

    for e_id in email_ids[-10:]:
        _, msg_data = mail.fetch(e_id, '(RFC822)')
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                subject = msg['subject']
                
                if subject in deja_vus: continue
                print(f"Traitement : {subject}")

                html_body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/html":
                            html_body = part.get_payload(decode=True).decode()
                else:
                    html_body = msg.get_payload(decode=True).decode()

                display_html = clean_html_content(html_body)

                # PROMPT IA : 10 questions + Thème basé sur le quiz
                prompt = f"""
                Analyse cette newsletter et génère un JSON STRICT :
                {{
                  "titre": "Titre court",
                  "theme_global": "GÉOPOLITIQUE, SOCIÉTÉ, ÉCONOMIE, PLANÈTE, TECH, CULTURE ou SPORT",
                  "questions": [
                    {{ "q": "Question ?", "options": ["A", "B", "C"], "correct": 0, "explication": "..." }}
                  ]
                }}
                Génère exactement 10 questions. Le theme_global doit correspondre au quiz.
                Texte : {html_body[:6000]}
                """
                
                try:
                    response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
                    clean_json = re.search(r'\{.*\}', response.text, re.DOTALL).group()
                    data = json.loads(clean_json)
                    data['html_affichage'] = display_html
                    
                    # Image d'illustration (Filtre les icônes)
                    img_urls = re.findall(r'src="([^"]+\.(?:jpg|png|jpeg)[^"]*)"', html_body)
                    img_src = ""
                    for url in img_urls:
                        if all(x not in url.lower() for x in ["logo", "avatar", "icon", "heart"]):
                            img_src = url
                            break
                    
                    local_img = download_image(img_src, e_id.decode())
                    data['image'] = local_img

                    # Sauvegarde
                    file_name = f"data/quiz-{e_id.decode()}.json"
                    os.makedirs('data', exist_ok=True)
                    with open(file_name, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)

                    manifest.append({
                        "date": datetime.now().strftime("%d/%m/%Y"),
                        "file": file_name,
                        "titre": data['titre'],
                        "titre_original": subject,
                        "image": local_img,
                        "theme": data['theme_global']
                    })
                except Exception as e:
                    print(f"Erreur : {e}")

    with open('manifest.json', 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    mail.logout()
    print("Mise à jour du dossier HUGO terminée.")

if __name__ == "__main__":
    process_emails()
