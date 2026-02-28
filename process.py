import os
import json
import re
from googleapiclient.discovery import build  # pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
import openai  # Pour Gemini, utilise google-generativeai
import google.generativeai as genai
from bs4 import BeautifulSoup
import imghdr
from email.mime.text import MIMEText
# Secrets : GEMINI_API_KEY, EMAIL_USER, EMAIL_PASS

genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-2.0-flash-exp')

THEMES = [
    "POLITIQUE EN FRANCE", "POLITIQUE INTERNATIONALE ET CONFLITS", "SOCIÉTÉ / FAITS DE SOCIÉTÉ",
    "ÉCONOMIE ET EMPLOI", "ENVIRONNEMENT ET CLIMAT", "SCIENCE, SANTÉ ET TECHNOLOGIE",
    "CULTURE ET MÉDIAS", "SPORT"
]

def clean_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    # Supprime headers/footers Gmail
    for tag in soup(['header', 'footer', '[class*="gmail"]', '[id*="gmail"]']):
        tag.decompose()
    # Nettoie styles parasites
    for tag in soup.find_all(style=re.compile(r'background|display|position|margin-top: -')):
        del tag['style']
    return str(soup.body) if soup.body else str(soup)

def extract_images(html):
    soup = BeautifulSoup(html, 'html.parser')
    imgs = [img['src'] for img in soup.find_all('img', src=True) if imghdr.what(None, h=img['src']) in ['jpeg', 'png']]
    return imgs[0] if imgs else 'default.jpg'  # Première image

def generate_questions(content):
    prompt = f"""
    Analyse cet article HugoDécrypte. Génère EXACTEMENT 10 questions QCM (4 options A B C D).
    Pour CHAQUE question :
    - Attribue UN des thèmes suivants : {', '.join(THEMES)}
    - Question courte, précise.
    - 1 bonne réponse.
    - Explication détaillée.
    Format JSON array :
    [{{"question": "...", "options": ["A...", "B...", "C...", "D..."], "correct": 0, "theme": "THÈME", "explanation": "..."}}]
    Contenu : {content[:4000]}
    """
    response = model.generate_content(prompt)
    return json.loads(response.text)

def process_email(service, msg_id):
    msg = service.users().messages().get(userId='me', id=msg_id).execute()
    payload = msg['payload']
    if 'parts' in payload:
        body = next(part['body']['data'] for part in payload['parts'] if part['mimeType'] == 'text/html')
    else:
        body = payload['body']['data']
    html = base64.urlsafe_b64decode(body).decode('utf-8')
    clean_content = clean_html(html)
    image = extract_images(html)
    
    questions = generate_questions(clean_content)
    data = {
        'content': clean_content,
        'questions': questions,
        'image': image
    }
    filename = f"quiz_{datetime.now().strftime('%Y%m%d')}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # Update manifest.json
    manifest = []
    if os.path.exists('manifest.json'):
        with open('manifest.json') as f:
            manifest = json.load(f)
    manifest.append({'file': filename, 'title': title_from_html(html), 'date': today_str(), 'image': image})
    with open('manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)
    
    print(f"Quiz généré : {filename}")

# Gmail API setup (à compléter avec creds)
def main():
    service = build('gmail', 'v1', credentials=creds)
    results = service.users().messages().list(userId='me', q='from:hugodecrypte@kessel.media label:HUGO').execute()
    for msg in results.get('messages', []):
        process_email(service, msg['id'])

if __name__ == '__main__':
    main()
