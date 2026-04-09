import logging
from datetime import datetime
from base64 import b64decode
from datetime import datetime
import os

# Définition du chemin du fichier config.ini
CORE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Save output csv files
def save_output(df, file_directory, file_name, extension: str = "csv", is_extension: str = True, is_date: str = True, **kwargs):
    """
    Saves a DataFrame to a CSV file with a date-based filename.

    Parameters:
    df (pd.DataFrame): The DataFrame to save.
    file_name (str): The base name of the CSV file.
    
    Returns:
    str: The full path of the saved CSV file.
    """
    
    # Get the current date and time
    current_time = datetime.now().strftime('%Y%m%d%H%M%S')
    
    # Create the full file name
    if is_date==True:
        if is_extension==True:
            full_file_name = f"{file_name}_{current_time}.{extension}"
        else:
            full_file_name = f"{file_name}_{current_time}"
    else:
        if is_extension==True:
            full_file_name = f"{file_name}.{extension}"
        else:
            full_file_name = f"{file_name}"
    
    # Create the full path
    full_path = os.path.join(file_directory, full_file_name)
    
    # Save the DataFrame to CSV
    df.to_csv(full_path, index=False, **kwargs)
    
    return full_path

def setup_logger(prog_name):
    """
    Configure et retourne un logger pour le programme.
    """
    if prog_name in logging.root.manager.loggerDict:
        return logging.getLogger(prog_name)  # Retourne le logger existant

    current_date = datetime.now().strftime('%Y%m%d')
    logs_path = os.path.join(CORE_DIR, "logs")
    
    # Créer le dossier logs s'il n'existe pas
    os.makedirs(logs_path, exist_ok=True)

    log_file_path = os.path.join(logs_path, f'{prog_name}_{current_date}.log')

    logger = logging.getLogger(prog_name)
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(f"[{prog_name}] %(asctime)s [%(levelname)s] %(message)s", datefmt='%Y-%m-%d %H:%M:%S')

    file_handler = logging.FileHandler(log_file_path, delay=True)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    logger.propagate = False

    return logger

def build_file_date_part(date_creation_brut: str) -> str:
    """
    Prend DateCreation brute (ex: '20241106160201...') et renvoie 'YYYY-MM-DD-HH-MM-SS'.
    Fallback: now si invalide.
    """
    date_str = (str(date_creation_brut or "")[:14]).strip()
    try:
        dt = datetime.strptime(date_str, "%Y%m%d%H%M%S")
    except ValueError:
        dt = datetime.now()
    return dt.strftime("%Y-%m-%d-%H-%M-%S")