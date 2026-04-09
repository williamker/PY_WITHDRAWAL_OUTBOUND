import glob
import os
import shutil
import subprocess
import sys
from datetime import datetime
import configparser
from pathlib import Path

# ---------------------- LOG GLOBAL ----------------------
# ---------------------- CONFIG ----------------------
BASE_DIR = Path(__file__).resolve().parents[1] # dossier PY_SEPA_ALLER
CONFIG_PATH = BASE_DIR / "config.ini"

if not CONFIG_PATH.exists():
    raise FileNotFoundError(f"config.ini introuvable : {CONFIG_PATH}")

config = configparser.ConfigParser()
config.read(CONFIG_PATH, encoding="utf-8")

ENV = config.get("settings", "ENV")

path_section = f"path.{ENV}"
if not config.has_section(path_section):
    raise ValueError(f"Section [{path_section}] manquante dans config.ini")

chemin_sources = config.get(path_section, "chemin_sources")
tmp_dir        = config.get(path_section, "tmp_dir")
output_dir     = config.get(path_section, "output_dir")
LOG_DIR        = config.get(path_section, "log_dir")
programs_dir   = config.get(path_section, "programs_dir")

# ---------------------- LOG GLOBAL ----------------------
os.makedirs(LOG_DIR, exist_ok=True)
log_path = os.path.join(LOG_DIR, f"PY_SEPA_ALLER_{datetime.now().strftime('%Y%m%d')}.log")

def log_global(msg: str):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {msg}\n")
    print(msg)


# ---------------------- TRAITEMENT ----------------------

print(f"[DEBUG] Dossier source : {chemin_sources}")
print(f"[DEBUG] Pattern       : {chemin_sources}SOURCE.MAMT*.TXT*")

os.makedirs(tmp_dir, exist_ok=True)
os.makedirs(output_dir, exist_ok=True)

# Recherche des fichiers sources
fichiers_sources = glob.glob(os.path.join(chemin_sources, "SOURCE.MAMT*.TXT*"))
print(f"[DEBUG] Fichiers trouvés : {len(fichiers_sources)}")

if not fichiers_sources:
    msg = "Aucun fichier SOURCE.MAMT*.TXT* trouvé -> fin du programme."
    print("[INFO]", msg)
    log_global(msg)
    sys.exit(0)

# Pour la log finale
fichiers_traites = []
fichiers_crees = []

# Parcourir chaque fichier trouvé
for fichier in fichiers_sources:

    nom_fichier = os.path.basename(fichier)
    fichiers_traites.append(nom_fichier)

    # Copier dans tmp
    shutil.copy(fichier, tmp_dir)

    # Préfixe MAMT00X
    prefixe = nom_fichier.split('.')[1]

    if prefixe == "MAMT001":
        script = os.path.join(programs_dir, "creat.py")
    elif prefixe == "MAMT002":
        script = os.path.join(programs_dir, "modif.py")
    elif prefixe == "MAMT003":
        script = os.path.join(programs_dir, "annul.py")
    elif prefixe == "MAMT004":
        script = os.path.join(programs_dir, "activ.py")
    else:
        continue


    # Exécuter le script
    subprocess.run([sys.executable, script, fichier], check=True)

    # Récupérer le dernier fichier créé dans output
    fichiers_output = sorted(
        glob.glob(os.path.join(output_dir, "*.csv")),
        key=os.path.getmtime,
        reverse=True
    )

    if fichiers_output:
        dernier = os.path.basename(fichiers_output[0])
        fichiers_crees.append(dernier)


# ---------------------- RÉCAP FINAL ----------------------

log_global("===== RÉCAPITULATIF TRAITEMENT SEPA_ALLER =====")

log_global(f"Démarrage PY_SEPA_ALLER - ENV={ENV}")
log_global(f"Sources  : {chemin_sources}")
log_global(f"TMP      : {tmp_dir}")
log_global(f"Output   : {output_dir}")
log_global(f"Programs : {programs_dir}")

log_global("Fichiers traités :")
for f in fichiers_traites:
    log_global(f" - {f}")

log_global("Fichiers créés :")
if fichiers_crees:
    for f in fichiers_crees:
        log_global(f" - {f}")
else:
    log_global(" - Aucun fichier créé")

log_global("================================================")

