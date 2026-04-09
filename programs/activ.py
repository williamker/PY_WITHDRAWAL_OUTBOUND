import os
import sys
from datetime import datetime
from io import StringIO
import re
import unicodedata
import configparser
from pathlib import Path
from utils import build_file_date_part
import pandas as pd


# --------- Logging utilities --------- #

def setup_logging(log_dir: str) -> str:
    """
    Initialise le fichier de log dans le répertoire demandé.
    """
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"activ_log_{datetime.now().strftime('%Y%m%d')}.log")
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
    Retourne '' si invalide ou vide.
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


# --------- Main processing --------- #

# --------- CONFIG ---------
BASE_DIR = Path(__file__).resolve().parents[1]  # .../PY_WITHDRAWAL_OUTBOUND
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

# template spécifique à activ.py
OUTPUT_TEMPLATE = config.get(output_section, "activ")

log_file = setup_logging(LOG_DIRECTORY)



def main() -> int:
    if len(sys.argv) < 2:
        msg = "Usage: python activ.py <fichier_source AC111 MAMT004>"
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
        # ---------- Header AC111 ----------
        colspecs_header = [
            (0, 2),
            (2, 37),
            (37, 72),
            (72, 86),
            (86, 100),
            (100, 129),
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

        # ---------- Contenu AC111 MAMT004 ----------
        colspecs = [
            (0, 2),
            (2, 9),
            (9, 44),
            (44, 79),
            (79, 87),   # DateEffetActivation
            (87, 122),
            (122, 157),
            (157, 161),
            (161, 301),
            (301, 306),
            (306, 308),
            (308, 312),
            (312, 328),
            (328, 398),
            (398, 414),
            (414, 484),
            (484, 554),
            (554, 659),
            (659, 661),
            (661, 731),
            (731, 801),
            (801, 1046),
            (1046, 1116),
            (1116, 1127),
            (1127, 1161),
            (1161, 1196),
            (1196, 1200),
            (1200, 1340),
            (1340, 1342),
            (1342, 1346),
            (1346, 1362),
            (1362, 1432),
            (1432, 1448),
            (1448, 1518),
            (1518, 1588),
            (1588, 1693),
            (1693, 1695),
            (1695, 1765),
            (1765, 1835),
            (1835, 2080),
            (2080, 2115),
            (2115, 2119),
            (2119, 2259),
            (2259, 2261),
            (2261, 2265),
            (2265, 2281),
            (2281, 2351),
            (2351, 2367),
            (2367, 2437),
            (2437, 2507),
            (2507, 2612),
            (2612, 2614),
            (2614, 2684),
            (2684, 2754),
            (2754, 2999),
        ]

        column_names = [
            "TypeDemande",
            "NumEnregistrement",
            "RefUniqueIntMandat",
            "RefUniqueMandat",
            "DateEffetActivation",
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

        df = df.fillna("")
        df["RefUniqueIntMandat"] = df["RefUniqueIntMandat"].astype(str).str.strip()
        df["TypeDemande"] = df["TypeDemande"].astype(str).str.strip()

        # Garder uniquement les lignes avec RUI non vide
        df = df[df["RefUniqueIntMandat"] != ""].copy()

        # ---------------- DEDOUBLONNAGE METIER (safe pandas) ----------------
        traitement_ts = pd.to_datetime(date_creation_brut[:8], format="%Y%m%d", errors="coerce")
        if pd.isna(traitement_ts):
            traitement_ts = pd.Timestamp.today().normalize()
        else:
            traitement_ts = traitement_ts.normalize()

        df["DateEffetActivation"] = df["DateEffetActivation"].astype(str).str.strip()
        df["_date_eff"] = pd.to_datetime(df["DateEffetActivation"], format="%Y%m%d", errors="coerce").dt.normalize()

        df["_num_enr"] = pd.to_numeric(df["NumEnregistrement"], errors="coerce")
        df["_line_order"] = range(len(df))

        def pick_rows(g: pd.DataFrame) -> pd.DataFrame:
            g = g.sort_values(["_date_eff", "_num_enr", "_line_order"])
            future = g[g["_date_eff"].notna() & (g["_date_eff"] > traitement_ts)]
            if len(future) > 0:
                max_eff = future["_date_eff"].max()
                g2 = g[g["_date_eff"] == max_eff].copy()
                return g2.tail(1)

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
        # -------------------------------------------------------------------


        nb_lignes = len(df)
        if nb_lignes == 0:
            msg = "Aucune ligne de mandat à traiter dans le fichier AC111 MAMT004."
            log_message(log_file, msg)
            print(msg)
            return 0

        # ---------- Entête PARTNER ----------
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

        # ---------- Lignes PARTNER ----------
        rows = []

        for _, r in df.iterrows():
            partner = [""] * TOTAL_FIELDS
            rui = sanitize_text(r.get("RefUniqueIntMandat", ""), max_len=75)
            partner[1] = "EXTID"
            partner[2] = rui

            # Statut / Type mandat
            partner[6] = "VALIDATED"
            partner[7] = "CORE"

            # Date de réactivation
            partner[9] = convert_yyyymmdd_to_iso_date(r.get("DateEffetActivation", ""))

            partner[12] = "P"
            partner[20] = "R"
            partner[23] = "EUR"

            # --- ALIGNEMENT STRUCTURE SUR modif.py ---
            # 1 champ vide entre EUR et INSURER_CO
            # partner.insert(30, "")

            # INSURER_CO + ICS
            partner[31] = "INSURER_CO"
            partner[32] = ics

            # Ajout champ RUI dans la zone ICS ;;;; RUI ;;; PARTICULAR
            # partner.insert(37, "")
            # rui = sanitize_text(r.get("RefUniqueIntMandat", ""), max_len=75)
            partner[37] = rui
            partner[42] = "PARTICULAR"

            # Champs constants
            partner[54] = "UNKNOWN"
            
            partner[62] = "FR"

            partner = partner[:TOTAL_FIELDS]
            rows.append(partner)

        detail_df = pd.DataFrame(rows)

        # Dédoublonnage final output (comme modif.py)
        before_out = len(detail_df)
        detail_df = detail_df.drop_duplicates(keep="last")
        log_message(log_file, f"Dedoublonnage output PARTNER: {before_out} -> {len(detail_df)} lignes")

        # ---------- Ecriture ----------
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
