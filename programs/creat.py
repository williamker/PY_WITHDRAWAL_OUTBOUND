import os
import sys
from datetime import datetime
from io import StringIO
import re
import unicodedata
import pandas as pd
from utils import build_file_date_part
import configparser
from pathlib import Path


# --------- Logging utilities --------- #

def setup_logging(log_dir: str) -> str:
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, f"creat_log_{datetime.now().strftime('%Y%m%d')}.log")


def log_message(log_file: str, message: str) -> None:
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
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).strip()
    if s == "" or s.lower() == "nan":
        return ""
    return s


def build_address_lines(num_voie: str, nom_rue: str) -> tuple[str, str, str]:
    """
    Construit Adresse1/2/3 (38 chars) à partir de num_voie + nom_rue,
    en supprimant 'nan' et en compressant les espaces.
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

# template de nom pour ce script
OUTPUT_TEMPLATE = config.get(output_section, "creat")

log_file = setup_logging(LOG_DIRECTORY)



def main() -> int:
    if len(sys.argv) < 2:
        msg = "Usage: python creat.py <fichier_source AC111>"
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

        # ---------- Contenu AC111 ----------
        colspecs = [
            (0, 2), (2, 9), (9, 44), (44, 79), (79, 80), (80, 115), (115, 150),
            (150, 158), (158, 162), (162, 166), (166, 201), (201, 209),
            (209, 244), (244, 248), (248, 388), (388, 393), (393, 395),
            (395, 399), (399, 415), (415, 485), (485, 501), (501, 571),
            (571, 641), (641, 746), (746, 748), (748, 818), (818, 888),
            (888, 1133), (1133, 1203), (1203, 1214), (1214, 1248), (1248, 1283),
            (1283, 1287), (1287, 1427), (1427, 1429), (1429, 1433), (1433, 1449),
            (1449, 1519), (1519, 1535), (1535, 1605), (1605, 1675), (1675, 1780),
            (1780, 1782), (1782, 1852), (1852, 1922), (1922, 2167), (2167, 2202),
            (2202, 2206), (2206, 2346), (2346, 2348), (2348, 2352), (2352, 2368),
            (2368, 2438), (2438, 2454), (2454, 2524), (2524, 2594), (2594, 2699),
            (2699, 2701), (2701, 2771), (2771, 2841), (2841, 3086), (3086, 3121),
        ]

        column_names = [
            "TypeDemande",
            "NumEnregistrement",
            "RefUniqueIntMandat",
            "RefUniqueMandat",
            "IdUniqueMandatmigre",
            "AncIdFinancier",
            "Filler",
            "DateValidite",
            "TypeMandat",
            "TypePaiement",
            "ContratSousJacent",
            "DateSignature",
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
            "Filler2",
            "CodePaysAdrPayeur",
            "Cpt1AdressePayeur",
            "Cpt2AdressePayeur",
            "Filler3",
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
            "Filler4",
            "CodePaysAdrSouscripteur",
            "Cpt1AdresseSouscripteur",
            "Cpt2AdresseSouscripteur",
            "Filler5",
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
            "Filler6",
            "CodePaysAdrCentreGestion",
            "Cpt1AdrCentreGestion",
            "Cpt2AdrCentreGestion",
            "Filler7",
            "OrigineMandat",
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

        # Fix .0 (comme modif.py)
        for col in ["NumVoiePayeur", "CodePostalPayeur", "DateSignature"]:
            if col in df.columns:
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace(r"\.0$", "", regex=True)
                    .str.strip()
                )

        df["TypeDemande"] = df["TypeDemande"].astype(str).str.strip()
        df["RefUniqueIntMandat"] = df["RefUniqueIntMandat"].astype(str).str.strip()

        # On ne garde que les lignes avec RUI non vide
        df = df[df["RefUniqueIntMandat"] != ""].copy()

        # ---------------- DEDOUBLONNAGE METIER (même logique que modif.py) ----------------
        # Date de traitement = date de création du fichier (entête AC111) -> en Timestamp (pandas)
        traitement_ts = pd.to_datetime(date_creation_brut[:8], format="%Y%m%d", errors="coerce")
        if pd.isna(traitement_ts):
            traitement_ts = pd.Timestamp.today().normalize()
        else:
            traitement_ts = traitement_ts.normalize()

        # DateValidite joue le rôle de "date effet" ici -> en datetime64[ns] normalisé (00:00:00)
        df["DateValidite"] = df["DateValidite"].astype(str).str.strip()
        df["_date_eff"] = pd.to_datetime(df["DateValidite"], format="%Y%m%d", errors="coerce").dt.normalize()

        # Tie-break : NumEnregistrement (dernier gagne)
        df["_num_enr"] = pd.to_numeric(df["NumEnregistrement"], errors="coerce")
        df["_line_order"] = range(len(df))  # stabilité si num_enr vide

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
        log_message(log_file, f"Dedoublonnage metier: {df_before} -> {len(df)} lignes (date_traitement={traitement_ts.strftime('%Y-%m-%d')})")

        # --------------------------------------------------------------------------------

        nb_lignes = len(df)
        if nb_lignes == 0:
            msg = "Aucune ligne de mandat à traiter dans le fichier AC111."
            log_message(log_file, msg)
            print(msg)
            return 0

        # ---------- Construction entête PARTNER ----------
        file_date_part = build_file_date_part(date_creation_brut)
        output_basename = OUTPUT_TEMPLATE.format(date=file_date_part)
        TOTAL_FIELDS = 63

        H01 = "PARTNER-MDT"
        H02 = "3"
        H03 = "0"
        H04 = date_creation_iso
        H05 = "INSURER_CO"   # comme modif.py
        H06 = output_basename
        H07 = str(nb_lignes)
        H08 = ""

        header_row = [H01, H02, H03, H04, H05, H06, H07, H08]
        header_row += [""] * (TOTAL_FIELDS - len(header_row))

        # ---------- Construction lignes PARTNER ----------
        rows = []

        for _, r in df.iterrows():
            partner = [""] * TOTAL_FIELDS
            rui = sanitize_text(r.get("RefUniqueIntMandat", ""), max_len=75)
            # 1 : EXTID
            partner[1] = "EXTID"

            # 2 : Identification -> RUI   
            partner[2] = rui

            # 6 : Statut -> WAITING_SIGN si DateSignature vide/invalide, sinon VALIDATED
            sig_iso = convert_yyyymmdd_to_iso_date(r.get("DateSignature", ""))
            partner[6] = "WAITING_SIGN" if sig_iso == "" else "VALIDATED"

            # 7 : Type mandat
            partner[7] = "CORE"

            # 12 : Origine
            partner[12] = "P"

            # 15 : Date signature (si valide)
            partner[15] = sig_iso

            # 20 : Type paiement
            partner[20] = "R"

            # 23 : Devise
            partner[23] = "EUR"

            # --- ALIGNEMENT STRUCTURE SUR modif.py ---
            # 1 champ vide entre EUR et INSURER_CO
            # partner.insert(30, "")

            # INSURER_CO + ICS
            partner[31] = "INSURER_CO"
            partner[32] = ics

            # Champ RUI supplémentaire dans zone ICS ;;;; RUI ;;; PARTICULAR
            # partner.insert(37, "")
            partner[37] = rui
            partner[42] = "PARTICULAR"

            # Nom titulaire
            partner[44] = sanitize_text(r.get("TitulaireComptePayeur", ""), max_len=70)

            # IBAN / BIC
            partner[47] = sanitize_text(r.get("IBANPayeur", ""), max_len=34)
            partner[48] = sanitize_text(r.get("BICPayeur", ""), max_len=15)

            # Mode com
            partner[54] = "UNKNOWN"

            # Adresse
            addr1, addr2, addr3 = build_address_lines(
                r.get("NumVoiePayeur", ""),
                r.get("NomRuePayeur", ""),
            )
            partner[55] = sanitize_text(addr1, max_len=38)
            partner[56] = sanitize_text(addr2, max_len=38)
            partner[57] = sanitize_text(addr3, max_len=38)
            partner[58] = ""

            # CP / Ville / Pays / FR constant
            partner[59] = sanitize_text(r.get("CodePostalPayeur", ""), max_len=20)
            partner[60] = sanitize_text(r.get("NomVillePayeur", ""), max_len=35)
            partner[61] = sanitize_text(r.get("CodePaysPayeur", ""), max_len=2)
            if not partner[61]:
                partner[61] = "FR"
            partner[62] = "FR"
            partner = partner[:TOTAL_FIELDS]
            rows.append(partner)

        detail_df = pd.DataFrame(rows)

        # Dédoublonnage output (comme modif.py)
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

        msg_ok = f"Fichier créé : {output_path} (lignes détail : {len(detail_df)})"
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
