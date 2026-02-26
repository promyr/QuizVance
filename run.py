# -*- coding: utf-8 -*-
"""
Facilitador de Execucao - Quiz Vance V2.0

Execute este arquivo para iniciar o app
"""

import os
import sys
import warnings
import traceback
from core.error_monitor import setup_global_error_hooks, log_exception, log_message, log_event
from core.app_paths import ensure_runtime_dirs, get_db_path
from core.database_v2 import Database
import io
from typing import cast

# Configurar encoding para UTF-8 no Windows
os.environ['PYTHONIOENCODING'] = 'utf-8'
if sys.platform == 'win32':
    stdout = cast(io.TextIOWrapper, sys.stdout)
    stderr = cast(io.TextIOWrapper, sys.stderr)
    stdout.reconfigure(encoding='utf-8', errors='replace')  # type: ignore[attr-defined]
    stderr.reconfigure(encoding='utf-8', errors='replace')  # type: ignore[attr-defined]

# Verificar se esta no diretorio correto
if not os.path.exists("main_v2.py") or not os.path.exists("config.py"):
    print("[ERRO] Execute este arquivo do diretorio raiz do projeto!")
    print("   cd simulador-pro-v2")
    print("   python run.py")
    sys.exit(1)

# Habilitar captura global de erros
setup_global_error_hooks()
log_message("App startup", f"Python {sys.version.split()[0]}")
ensure_runtime_dirs()

# Verificar dependencias
try:
    warnings.filterwarnings(
        "ignore",
        category=ResourceWarning,
        module=r"flet\.messaging\.flet_socket_server"
    )
    warnings.filterwarnings(
        "ignore",
        category=DeprecationWarning,
        module=r"main_v2"
    )
    import flet
except ImportError:
    print("[ERRO] Flet nao instalado!")
    print("        pip install -r requirements.txt")
    sys.exit(1)

# Verificar se banco existe
db_path = get_db_path()
if not db_path.exists():
    print("[WARN] Banco de dados nao encontrado!")
    print("       Inicializando banco local...")
    print()
    
    try:
        Database(str(db_path)).iniciar_banco()
    except Exception as e:
        print(f"[ERRO] Erro no setup: {e}")
        sys.exit(1)

# Executar aplicacao
print("[INFO] Iniciando Quiz Vance V2.0...")
print()

from main_v2 import main
import flet as ft

try:
    log_event("app_start", f"python={sys.version.split()[0]}")
    ft.app(target=main, assets_dir="assets")
except Exception as ex:
    log_exception(ex, "run.py ft.run")
    print(f"[ERRO] Falha ao iniciar app: {ex}")
    traceback.print_exc()
    sys.exit(1)
