import os
import sys
from datetime import datetime
from io import StringIO
import re
import unicodedata
import pandas as pd
import configparser
from pathlib import Path
from utils import build_file_date_part


# --------- Logging utilities --------- #

def setup_logging(log_dir: str) -> str:
    """
    Initialise le fichier de log dans le répertoire demandé.
    """
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"modif_log_{datetime.now().strftime('%Y%m%d')}.log")
    return log_file


def log_message(log_file: str, message: str) -> None:
    """
    Ecrit un message dans le fichier de log.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


# --------- Helper functions --------- #

_ALLOWED_RE = re.compile(r"[^A-Z0-9 .]+")  # on autorise espace + point

_LIGATURES_MAP = {
    "œ": "oe", "Œ": "OE",
    "æ": "ae", "Æ": "AE",
    "ß": "ss",
}

def _fix_mojibake_if_any(s: str) -> str:
    """
    Si le fichier est en UTF-8 mais lu en latin1, on obtient souvent des 'Ã', 'Â', etc.
    On tente une réparation safe : latin1 -> utf-8.
    Si ça échoue, on garde la chaîne telle quelle.
    """
    if "Ã" in s or "Â" in s or "�" in s:
        try:
            return s.encode("latin1").decode("utf-8")
        except Exception:
            return s
    return s

def _strip_accents(s: str) -> str:
    for k, v in _LIGATURES_MAP.items():
        s = s.replace(k, v)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s

def _smart_truncate(s: str, max_len: int) -> str:
    """
    Tronque sans couper un mot :
    - coupe à max_len
    - si on est au milieu d’un mot, on revient au dernier espace
    """
    if len(s) <= max_len:
        return s
    cut = s[:max_len].rstrip()
    # si on a coupé en plein mot, revenir au dernier espace
    if max_len < len(s) and max_len > 0 and s[max_len-1] != " " and s[max_len] != " ":
        last_space = cut.rfind(" ")
        if last_space > 0:
            cut = cut[:last_space].rstrip()
    return cut

def sanitize_text(value, max_len: int | None = None) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        s = ""
    else:
        s = str(value)

    if s.strip().lower() == "nan":
        return ""

    # séparateurs -> espace
    for ch in [";", "\n", "\r", "\t", ","]:
        s = s.replace(ch, " ")

    s = s.strip()

    # 1) réparer éventuellement l’encodage
    s = _fix_mojibake_if_any(s)

    # 2) désaccentuer
    s = _strip_accents(s)

    # 3) upper
    s = s.upper()

    # 4) enlever les caractères interdits SANS insérer d’espace (évite CUMMA RATAI)
    s = _ALLOWED_RE.sub("", s)

    # 5) compresser les espaces
    s = " ".join(s.split())

    # 6) règle métier : "M." -> "M" (comme ton attendu 3)
    s = re.sub(r"\bM\.\b", "M", s)

    # 7) éviter "M ." (si jamais)
    s = s.replace(" .", ".")

    # 8) tronquage intelligent (évite "SPECIAUX A")
    if max_len is not None:
        s = _smart_truncate(s, max_len)

    return s



def convert_yyyymmdd_to_iso_date(date_str: str) -> str:
    """
    Convertit 'YYYYMMDD' -> 'YYYY-MM-DD'.
    Retourne '' si la date est invalide ou vide.
    """
    if not date_str:
        return ""
    date_str = str(date_str).strip()
    if len(date_str) < 8:
        return ""
    date_str = date_str[:8]
    try:
        dt = datetime.strptime(date_str, "%Y%m%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return ""


def convert_yyyymmddhhmmss_to_iso_datetime(date_str: str, tz_offset: str = "+02:00") -> str:
    """
    Convertit 'YYYYMMDDHHMMSS' -> 'YYYY-MM-DDThh:mm:ss.000+02:00'
    (format attendu en entête PARTNER).
    """
    if not date_str:
        return ""
    date_str = str(date_str).strip()
    if len(date_str) < 14:
        return ""
    date_str = date_str[:14]
    try:
        dt = datetime.strptime(date_str, "%Y%m%d%H%M%S")
        return dt.strftime(f"%Y-%m-%dT%H:%M:%S.000{tz_offset}")
    except ValueError:
        return ""

def clean_optional_prefix(value) -> str:
    """Transforme None/NaN/'nan' en ''."""
    if value is None:
        return ""
    s = str(value).strip()
    if s == "" or s.lower() == "nan":
        return ""
    return s

def build_address_lines(num_voie: str, nom_rue: str) -> tuple[str, str, str]:
    """
    Construit Adresse1/Adresse2/Adresse3 (champs 51/52/53) à partir
    du numéro de voie et du libellé de la rue.

    - concatène "num_voie nom_rue"
    - nettoie la chaîne
    - découpe par tronçons de 38 caractères
    """
    num_voie = clean_optional_prefix(num_voie)
    nom_rue = clean_optional_prefix(nom_rue)

    full = f"{num_voie} {nom_rue}".strip()
    full = sanitize_text(full)

    addr1 = full[:38]
    addr2 = full[38:76] if len(full) > 38 else ""
    addr3 = full[76:114] if len(full) > 76 else ""

    return addr1, addr2, addr3


# --------- Main processing --------- #

# --------- CONFIG ---------
BASE_DIR = Path(__file__).resolve().parents[1]  # .../PY_SEPA_ALLER
CONFIG_PATH = BASE_DIR / "config.ini"

if not CONFIG_PATH.exists():
    raise FileNotFoundError(f"config.ini introuvable : {CONFIG_PATH}")

config = configparser.ConfigParser()
config.read(CONFIG_PATH, encoding="utf-8")

ENV = config.get("settings", "ENV")  # obligatoire

path_section = f"path.{ENV}"
output_section = f"output.{ENV}"

if not config.has_section(path_section):
    raise ValueError(f"Section [{path_section}] manquante dans config.ini")
if not config.has_section(output_section):
    raise ValueError(f"Section [{output_section}] manquante dans config.ini")

LOG_DIRECTORY = config.get(path_section, "log_dir")
OUTPUT_DIR = config.get(path_section, "output_dir")

# template spécifique à modif.py
OUTPUT_TEMPLATE = config.get(output_section, "modif")

log_file = setup_logging(LOG_DIRECTORY)



def main() -> int:
    # Vérification des arguments
    if len(sys.argv) < 2:
        msg = "Usage: python modif.py <fichier_source AC111 MAMT002>"
        log_message(log_file, msg)
        print(msg)
        return 1

    fichier_source = sys.argv[1]

    if not os.path.exists(fichier_source):
        msg = f"Fichier source non trouvé : {fichier_source}"
        log_message(log_file, msg)
        print(msg)
        return 2

    log_message(log_file, f"Fichier source récupéré : {fichier_source}")

    try:
        # ---------- Lecture de l'en-tête AC111 ---------- #
        # On suppose que l'entête MAMT002 reprend la même logique que MAMT001 :
        # 01 + ICS + IdEmetrice + DateCreation(YYYYMMDDHHMMSS) + IdFichier + NBEnregistrement
        colspecs_header = [
            (0, 2),   # TypeEnregistrement
            (2, 37),  # IdCrediteur (ICS + éventuellement compléments)
            (37, 72), # IdEmetrice
            (72, 86), # DateCreation (YYYYMMDDHHMMSS)
            (86, 100),# IdFichier
            (100, 129)  # NBEnregistrement (non utilisé ici)
        ]
        column_names_header = [
            "TypeEnregistrement",
            "IdCrediteur",
            "IdEmetrice",
            "DateCreation",
            "IdFichier",
            "NBEnregistrement",
        ]

        with open(fichier_source, "r", encoding="latin1") as f:
            first_line = f.readline().rstrip("\n")

        df_header = pd.read_fwf(
            StringIO(first_line),
            colspecs=colspecs_header,
            names=column_names_header,
        )

        date_creation_brut = str(df_header["DateCreation"].iloc[0]).strip()
        date_creation_iso = convert_yyyymmddhhmmss_to_iso_datetime(date_creation_brut)
        ics = sanitize_text(df_header["IdCrediteur"].iloc[0], max_len=35)

        # ---------- Lecture du contenu AC111 MAMT002 ---------- #
        # colspecs repris de ton ancien modif.py
        colspecs = [
            (0, 2),    # TypeDemande
            (2, 9),    # NumEnregistrement
            (9, 44),   # RefUniqueIntMandat
            (44, 79),  # RefUniqueMandat
            (79, 87),  # DateEffetModification
            (87, 122), # ContratSousJacent
            (122, 157),# RefDebiteur
            (157, 161),# CivilitePayeur
            (161, 301),# NomPayeur
            (301, 306),# LanguePayeur
            (306, 308),# CodePaysPayeur
            (308, 312),# TypeAdressePayeur
            (312, 328),# NumVoiePayeur
            (328, 398),# NomRuePayeur
            (398, 414),# CodePostalPayeur
            (414, 484),# NomVillePayeur
            (484, 554),# DptPayeur
            (554, 659),# Filler1
            (659, 661),# CodePaysAdrPayeur
            (661, 731),# Cpt1AdressePayeur
            (731, 801),# Cpt2AdressePayeur
            (801, 1046),# Filler2
            (1046, 1116),# TitulaireComptePayeur
            (1116, 1127),# BICPayeur
            (1127, 1161),# IBANPayeur
            (1161, 1196),# RefSouscripeur
            (1196, 1200),# CiviliteSouscripteur
            (1200, 1340),# NomSouscripteur
            (1340, 1342),# CodePaysSouscripteur
            (1342, 1346),# TypeAdresseSouscripteur
            (1346, 1362),# NumVoieSouscripteur
            (1362, 1432),# NomRueSouscripteur
            (1432, 1448),# CodePostalSouscripteur
            (1448, 1518),# NomVilleSouscripteur
            (1518, 1588),# DptSouscripteur
            (1588, 1693),# Filler3
            (1693, 1695),# CodePaysAdrSouscripteur
            (1695, 1765),# Cpt1AdresseSouscripteur
            (1765, 1835),# Cpt2AdresseSouscripteur
            (1835, 2080),# Filler4
            (2080, 2115),# RefCentreGestionContrat
            (2115, 2119),# CiviliteCentreGestion
            (2119, 2259),# NomCentreGestion
            (2259, 2261),# CodePaysCentreGestion
            (2261, 2265),# TypeAdrCentreGestion
            (2265, 2281),# NumVoieCentreGestion
            (2281, 2351),# NomRueCentreGestion
            (2351, 2367),# CodePostalCentreGestion
            (2367, 2437),# NomVilleCentreGestion
            (2437, 2507),# DptCentreGestion
            (2507, 2612),# Filler5
            (2612, 2614),# CodePaysAdrCentreGestion
            (2614, 2684),# Cpt1AdrCentreGestion
            (2684, 2754),# Cpt2AdrCentreGestion
            (2754, 2999) # Filler6
        ]

        column_names = [
            "TypeDemande",
            "NumEnregistrement",
            "RefUniqueIntMandat",
            "RefUniqueMandat",
            "DateEffetModification",
            "ContratSousJacent",
            "RefDebiteur",
            "CivilitePayeur",
            "NomPayeur",
            "LanguePayeur",
            "CodePaysPayeur",
            "TypeAdressePayeur",
            "NumVoiePayeur",
            "NomRuePayeur",
            "CodePostalPayeur",
            "NomVillePayeur",
            "DptPayeur",
            "Filler1",
            "CodePaysAdrPayeur",
            "Cpt1AdressePayeur",
            "Cpt2AdressePayeur",
            "Filler2",
            "TitulaireComptePayeur",
            "BICPayeur",
            "IBANPayeur",
            "RefSouscripeur",
            "CiviliteSouscripteur",
            "NomSouscripteur",
            "CodePaysSouscripteur",
            "TypeAdresseSouscripteur",
            "NumVoieSouscripteur",
            "NomRueSouscripteur",
            "CodePostalSouscripteur",
            "NomVilleSouscripteur",
            "DptSouscripteur",
            "Filler3",
            "CodePaysAdrSouscripteur",
            "Cpt1AdresseSouscripteur",
            "Cpt2AdresseSouscripteur",
            "Filler4",
            "RefCentreGestionContrat",
            "CiviliteCentreGestion",
            "NomCentreGestion",
            "CodePaysCentreGestion",
            "TypeAdrCentreGestion",
            "NumVoieCentreGestion",
            "NomRueCentreGestion",
            "CodePostalCentreGestion",
            "NomVilleCentreGestion",
            "DptCentreGestion",
            "Filler5",
            "CodePaysAdrCentreGestion",
            "Cpt1AdrCentreGestion",
            "Cpt2AdrCentreGestion",
            "Filler6",
        ]

        df = pd.read_fwf(
            fichier_source,
            colspecs=colspecs,
            header=None,
            names=column_names,
            skiprows=1,
            encoding="latin1",
        )

        for col in ["NumVoiePayeur", "CodePostalPayeur"]:
            if col in df.columns:
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace(r"\.0$", "", regex=True)
                    .str.strip()
                )

        # Normalisation de base
        # for col in ["NumVoiePayeur", "NomRuePayeur", "CodePostalPayeur", "NomVillePayeur"]:
        #     if col in df.columns:
        #         df[col] = df[col].astype(str)

        df = df.fillna("")

        df["TypeDemande"] = df["TypeDemande"].astype(str).str.strip()
        df["RefUniqueIntMandat"] = df["RefUniqueIntMandat"].astype(str).str.strip()

        # On ne garde que les lignes avec RUI non vide
        df = df[df["RefUniqueIntMandat"] != ""].copy()
        # ---------------- DEDOUBLONNAGE METIER ----------------
        # Date de traitement = date de création du fichier (entête AC111) -> Timestamp pandas (safe)
        traitement_ts = pd.to_datetime(date_creation_brut[:8], format="%Y%m%d", errors="coerce")
        if pd.isna(traitement_ts):
            traitement_ts = pd.Timestamp.today().normalize()
        else:
            traitement_ts = traitement_ts.normalize()

        # Parsing date effet + nettoyage -> datetime64[ns] normalisé
        df["DateEffetModification"] = df["DateEffetModification"].astype(str).str.strip()
        df["_date_eff"] = pd.to_datetime(df["DateEffetModification"], format="%Y%m%d", errors="coerce").dt.normalize()

        # Tie-break : NumEnregistrement (dernier gagne)
        df["_num_enr"] = pd.to_numeric(df["NumEnregistrement"], errors="coerce")
        df["_line_order"] = range(len(df))  # stabilité si num_enr vide

        def pick_rows(g: pd.DataFrame) -> pd.DataFrame:
            g = g.sort_values(["_date_eff", "_num_enr", "_line_order"])

            # Si on a au moins une date future -> ne garder QUE la date_eff max future
            future = g[g["_date_eff"].notna() & (g["_date_eff"] > traitement_ts)]
            if len(future) > 0:
                max_eff = future["_date_eff"].max()
                g2 = g[g["_date_eff"] == max_eff].copy()
                return g2.tail(1)

            # Sinon -> garder la date_eff max (<=J ou NaT)
            if g["_date_eff"].notna().any():
                max_eff = g["_date_eff"].max()
                g2 = g[g["_date_eff"] == max_eff].copy()
                return g2.tail(1)

            return g.tail(1)

        df_before = len(df)
        df = (
            df.groupby("RefUniqueIntMandat", group_keys=False)
            .apply(pick_rows)
            .reset_index(drop=True)
        )

        df = df.drop(columns=["_date_eff", "_num_enr", "_line_order"], errors="ignore")
        log_message(
            log_file,
            f"Dedoublonnage metier: {df_before} -> {len(df)} lignes (date_traitement={traitement_ts.strftime('%Y-%m-%d')})"
        )
        # ------------------------------------------------------



        nb_lignes = len(df)
        if nb_lignes == 0:
            msg = "Aucune ligne de mandat à traiter dans le fichier AC111 MAMT002."
            log_message(log_file, msg)
            print(msg)
            return 0

        # ---------- Construction de l'entête PARTNER ---------- #
        file_date_part = build_file_date_part(date_creation_brut)
        output_basename = OUTPUT_TEMPLATE.format(date=file_date_part)

        TOTAL_FIELDS = 63
        H01 = "PARTNER-MDT"
        H02 = "3"
        H03 = "0"
        H04 = date_creation_iso
        H05 = "INSURER_CO"
        H06 = output_basename
        H07 = str(nb_lignes)
        H08 = ""

        header_row = [H01, H02, H03, H04, H05, H06, H07, H08]
        header_row += [""] * (TOTAL_FIELDS - len(header_row))

        # ---------- Construction des enregistrements de ligne PARTNER ---------- #
        rows = []

        for _, r in df.iterrows():
            # Gabarit EXACT de l'ATTENDU : 63 champs
            partner = [""] * TOTAL_FIELDS

            # RUI
            rui = sanitize_text(r.get("RefUniqueIntMandat", ""), max_len=75)

            # 1 : Type d'identification -> EXTID
            partner[1] = "EXTID"

            # 2 : Identification -> RUI AC111
            partner[2] = sanitize_text(r.get("RefUniqueIntMandat", ""), max_len=75)

            # 3 : RUM -> vide en ALLER (sera renvoyée via AC112)
            # 4,5 : dates création / modification -> non renseignées en ALLER (SFD)

            # 6 : Statut -> VALIDATED pour MAMT002
            partner[6] = "VALIDATED"

            # 7 : Type de mandat -> CORE
            partner[7] = "CORE"

            # 12 : Origine -> P
            partner[12] = "P"

            # 15 : Date de signature -> NE PAS RENSEIGNER pour MAMT002 (SFD : seulement MAMT001)
            # partner[15] = ""

            # 20 : Type de paiement -> R (récurrent)
            partner[20] = "R"

                        # 23 : Devise -> EUR
            partner[23] = "EUR"

            # ------------------------------------------------------------
            # AJUSTEMENT STRUCTURE : ajout 1 champ vide entre EUR et INSURER_CO
            # (ça ajoute le ";" manquant)
            # Ajoute 1 champ vide entre EUR et INSURER_CO (le ";" manquant)
            partner.insert(30, "")

            # INSURER_CO + ICS
            partner[31] = "INSURER_CO"
            partner[32] = ics

            # --- OBJECTIF : ICS ;;;; RUI ;;; PARTICULAR ---
            # On crée 1 champ supplémentaire (celui du RUI) à l'index où doit tomber RUI
            # ICS est à 32 -> 4 vides => champs 33..36 vides -> RUI doit être champ 37
            partner.insert(37, "")  # création du champ RUI (et décalage de tout ce qui suit)

            rui = sanitize_text(r.get("RefUniqueIntMandat", ""), max_len=75)
            partner[37] = rui

            # Après RUI : 3 vides => champs 38..40 vides -> PARTICULAR doit être champ 41
            partner[42] = "PARTICULAR"

            # Ensuite on décale les index de tes champs “métier” par rapport à l’ancien code
            partner[44] = sanitize_text(r.get("TitulaireComptePayeur", ""), max_len=70)  # Nom (PARTICULAR +2)
            partner[47] = sanitize_text(r.get("IBANPayeur", ""), max_len=34)            # IBAN (PARTICULAR +5)
            partner[48] = sanitize_text(r.get("BICPayeur", ""), max_len=15)             # BIC  (PARTICULAR +6)

            partner[54] = "UNKNOWN"                                                    # (ancien 50 -> +3)

            addr1, addr2, addr3 = build_address_lines(r.get("NumVoiePayeur", ""), r.get("NomRuePayeur", ""))
            partner[55] = sanitize_text(addr1, max_len=38)                             # (ancien 51 -> +3)
            partner[56] = sanitize_text(addr2, max_len=38)
            partner[57] = sanitize_text(addr3, max_len=38)
            partner[58] = ""
            partner[59] = sanitize_text(r.get("CodePostalPayeur", ""), max_len=20)      # (ancien 55 -> +3)
            partner[60] = sanitize_text(r.get("NomVillePayeur", ""), max_len=35)        # (ancien 56 -> +3)
            partner[61] = sanitize_text(r.get("CodePaysPayeur", ""), max_len=2)         # (ancien 57 -> +3)
            if not partner[61]:
                partner[61] = "FR"
            partner[62] = "FR"                                                         # (ancien 58 -> +3)


            partner = partner[:TOTAL_FIELDS]
            rows.append(partner)

        detail_df = pd.DataFrame(rows)

        # Dédoublonnage final sur les lignes réellement exportées à PARTNER
        before_out = len(detail_df)
        detail_df = detail_df.drop_duplicates(keep="last")
        log_message(log_file, f"Dedoublonnage output PARTNER: {before_out} -> {len(detail_df)} lignes")

        # ---------- Ecriture du fichier de sortie ---------- #
        output_dir = OUTPUT_DIR
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, output_basename)


        with open(output_path, "w", encoding="utf-8", newline="") as out:
            out.write(";".join(header_row) + "\n")
            detail_df.to_csv(out, index=False, header=False, sep=";", na_rep="")

        msg_ok = f"Fichier créé : {output_path} (lignes détail : {nb_lignes})"
        log_message(log_file, msg_ok)
        print(msg_ok)
        return 0

    except Exception as e:
        error_message = f"Erreur lors du traitement : {e}"
        log_message(log_file, error_message)
        print(error_message)
        return 2


if __name__ == "__main__":
    sys.exit(main())
