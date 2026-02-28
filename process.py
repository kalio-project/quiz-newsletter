import os, json, re, time
from google import genai
from bs4 import BeautifulSoup
from datetime import datetime

# --- CONFIGURATION ---
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
SOURCE_FOLDER = "newsletters_html"

def run():
    if not os.path.exists('data'): os.makedirs('data')
    try:
        with open('manifest.json', 'r', encoding='utf-8') as f: manifest = json.load(f)
    except: manifest = []
    
    deja_vus = [m.get("titre_original") for m in manifest]

    if not os.path.exists(SOURCE_FOLDER):
        os.makedirs(SOURCE_FOLDER)
        return

    files = [f for f in os.listdir(SOURCE_FOLDER) if f.endswith(('.htm', '.html')) and f not in deja_vus]

    if not files:
        print("✅ Aucun nouveau fichier à traiter.")
        return

    # On traite un fichier
    file_name = files[0]
    file_path = os.path.join(SOURCE_FOLDER, file_name)
    
    print(f"📄 Lecture complète de : {file_name}")
    with open(file_path, 'r', encoding='utf-8') as f:
        html_complet = f.read()

    # --- 1. EXTRACTION DU TEXTE BRUT COMPLET (SANS LIMITE) ---
    soup = BeautifulSoup(html_complet, 'html.parser')
    for tag in soup(["script", "style"]): tag.decompose()
    # On récupère l'intégralité du texte
    texte_brut_complet = ' '.join(soup.get_text(separator=' ').split())
    
    # --- 2. APPEL IA AVEC LE TEXTE INTÉGRAL ---
    print(f"🤖 Analyse IA du texte complet ({len(texte_brut_complet)} caractères)...")
    prompt = "Génère un quiz JSON de 10 questions sur ce texte. Format: {\"theme_global\": \"\", \"titre\": \"\", \"questions\": [{\"q\": \"\", \"options\": [\"\", \"\", \"\", \"\"], \"correct\": 0, \"explication\": \"\"}]}"

    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=f"{prompt}\n\nTexte complet: {texte_brut_complet}"
        )
        
        json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if json_match:
            quiz_data = json.loads(json_match.group())
            
            # --- 3. ON INCLUT LE HTML ORIGINAL POUR L'AFFICHAGE SITE ---
            quiz_data['html_affichage'] = html_complet 
            
            quiz_id = datetime.now().strftime("%Y%m%d-%H%M")
            dest_path = f"data/quiz-{quiz_id}.json"
            
            with open(dest_path, 'w', encoding='utf-8') as f:
                json.dump(quiz_data, f, ensure_ascii=False)

            manifest.append({
                "date": datetime.now().strftime("%d %b %Y"),
                "file": dest_path,
                "titre": quiz_data.get('titre', file_name),
                "titre_original": file_name,
                "theme": quiz_data.get('theme_global', 'ACTU')
            })
            
            with open('manifest.json', 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            
            print(f"✅ Quiz généré avec succès à partir du texte complet !")
            
    except Exception as e:
        print(f"⚠️ Erreur : {e}")

if __name__ == "__main__":
    run()
