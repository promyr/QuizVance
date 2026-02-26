# -*- coding: utf-8 -*-
"""
Quiz Vance V2.0 - Arquivo principal.
"""

import flet as ft
import os
import asyncio
import random
import time
import datetime
import hashlib
import json
import textwrap
import unicodedata
from typing import Optional, Any

from config import CORES, AI_PROVIDERS, DIFICULDADES, get_level_info
from core.database_v2 import Database
from core.backend_client import BackendClient
from core.error_monitor import log_exception, log_event
from core.app_paths import ensure_runtime_dirs, get_db_path, get_data_dir
from core.ai_service_v2 import AIService, create_ai_provider
from core.sounds import create_sound_manager
from core.library_service import LibraryService
from core.platform_helper import is_android, is_desktop, get_platform
from core.filter_taxonomy import get_quiz_filter_taxonomy
from core.repositories.question_progress_repository import QuestionProgressRepository
from core.services.mock_exam_report_service import MockExamReportService
from core.services.mock_exam_service import MockExamService
from core.services.quiz_filter_service import QuizFilterService
from ui.views.login_view_v2 import LoginView
from ui.views.review_session_view_v2 import build_review_session_body
from ui.design_system import DS, ds_card, ds_btn_primary, ds_btn_ghost, ds_empty_state, ds_toast, ds_bottom_sheet, ds_section_title, ds_stat_card, ds_badge, ds_divider, ds_skeleton, ds_skeleton_card, ds_chip, ds_btn_secondary, ds_progress_bar, ds_icon_btn

# Rotas da bottom bar (Android) / sidebar principal (Desktop) - maximo 5
APP_ROUTES = [
    ("/home",       "Inicio",    ft.Icons.HOME_OUTLINED),
    ("/quiz",       "Questoes",  ft.Icons.QUIZ_OUTLINED),
    ("/revisao",    "Revisao",   ft.Icons.STYLE_OUTLINED),
    ("/flashcards", "Cards",     ft.Icons.STYLE_OUTLINED),
    ("/mais",       "Mais",      ft.Icons.GRID_VIEW_OUTLINED),
]

# Rotas secundarias - acessiveis via /mais (hub)
APP_ROUTES_SECONDARY = [
    ("/flashcards",  "Flashcards",    ft.Icons.STYLE_OUTLINED),
    ("/open-quiz",   "Dissertativo",  ft.Icons.EDIT_NOTE_OUTLINED),
    ("/library",     "Biblioteca",    ft.Icons.LOCAL_LIBRARY_OUTLINED),
    ("/stats",       "Estatisticas",  ft.Icons.INSIGHTS_OUTLINED),
    ("/profile",     "Perfil",        ft.Icons.PERSON_OUTLINE),
    ("/ranking",     "Ranking",       ft.Icons.EMOJI_EVENTS_OUTLINED),
    ("/conquistas",  "Conquistas",    ft.Icons.MILITARY_TECH_OUTLINED),
    ("/plans",       "Planos",        ft.Icons.STARS_OUTLINED),
    ("/settings",    "Configuracoes", ft.Icons.SETTINGS_OUTLINED),
]

_ROUTE_ALIASES = {
    "/panel": "/home",
    "/painel": "/home",
    "/inicio": "/home",
    "/questoes": "/quiz",
    "/revisao/caderno-erros": "/revisao/erros",
    "/revisao/caderno_erros": "/revisao/erros",
    "/revisao/marcados": "/revisao/marcadas",
}


def _normalize_route_path(route: Optional[str]) -> str:
    raw = str(route or "").strip()
    if not raw:
        return "/home"
    path = raw.split("?", 1)[0].split("#", 1)[0].strip()
    if not path:
        return "/home"
    if not path.startswith("/"):
        path = f"/{path}"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return _ROUTE_ALIASES.get(path.lower(), path)


def _color(name: str, dark: bool):
    if dark:
        mapping = {
            "fundo": CORES["fundo_escuro"],
            "card": CORES["card_escuro"],
            "texto": CORES["texto_escuro"],
            "texto_sec": CORES["texto_sec_escuro"],
        }
        return mapping.get(name, CORES.get(name, "#FFFFFF"))
    return CORES.get(name, "#000000")


_MOJIBAKE_MARKERS = ("Ã", "Â", "â", "ð", "œ", "™")


def _fix_mojibake_text(value: str) -> str:
    if not isinstance(value, str) or not value:
        return value
    if not any(marker in value for marker in _MOJIBAKE_MARKERS):
        return value
    current = value
    try:
        candidate = current.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
        if candidate and candidate != current:
            current = candidate
    except Exception:
        pass

    # Sequencias frequentes de texto quebrado em PT-BR.
    sequence_map = {
        "\u00c3\u0192\u00c6\u2019\u00c3\u201a\u00c2\u00b5": "o",
        "\u00c3\u0192\u00c6\u2019\u00c3\u201a\u00c2\u00a3": "a",
        "\u00c3\u0192\u00c6\u2019\u00c3\u201a\u00c2\u00a7": "c",
        "\u00c3\u0192\u00c6\u2019\u00c3\u201a\u00c2\u00a1": "a",
        "\u00c3\u0192\u00c6\u2019\u00c3\u201a\u00c2\u00a9": "e",
        "\u00c3\u0192\u00c6\u2019\u00c3\u201a\u00c2\u00ad": "i",
        "\u00c3\u0192\u00c6\u2019\u00c3\u201a\u00c2\u00ba": "u",
        "\u00c3\u0192\u00c2\u00b5": "o",
        "\u00c3\u0192\u00c2\u00a3": "a",
        "\u00c3\u0192\u00c2\u00a7": "c",
        "\u00c3\u0192\u00c2\u00a1": "a",
        "\u00c3\u0192\u00c2\u00a9": "e",
        "\u00c3\u0192\u00c2\u00ad": "i",
        "\u00c3\u0192\u00c2\u00ba": "u",
        "\u00c3\u00b5": "o",
        "\u00c3\u00a3": "a",
        "\u00c3\u00a7": "c",
        "\u00c3\u00a1": "a",
        "\u00c3\u00a9": "e",
        "\u00c3\u00ad": "i",
        "\u00c3\u00ba": "u",
        "\u00c3\u00aa": "e",
        "\u00c3\u00b4": "o",
        "\u00c3\u00b3": "o",
        "\u00c3\u00a2": "a",
        "\u00c3\u00a0": "a",
        "\u00e2\u20ac\u00a6": "...",
        "\u00e2\u20ac\u201d": "-",
        "\u00e2\u20ac\u201c": "-",
        "\u00e2\u20ac\u00a2": "-",
        "\u00c3\u00a2\u20ac\u201d\u00c2\u2020": "",
        "\u00c2": "",
    }
    for broken, clean in sequence_map.items():
        if broken in current:
            current = current.replace(broken, clean)

    # Fallback para caracteres residuais comuns de mojibake.
    residue_map = {
        "µ": "o",
        "¡": "a",
        "£": "a",
        "§": "c",
        "©": "e",
        "ª": "a",
        "º": "o",
        "­": "i",
        "ƒ": "",
        "Æ": "",
        "¢": "",
        "€": "",
        "™": "",
        "â": "",
        "�": "",
        "◊": "",
    }
    if any(ch in current for ch in residue_map.keys()):
        current = "".join(residue_map.get(ch, ch) for ch in current)
    current = "".join(
        ch for ch in unicodedata.normalize("NFKD", current)
        if not unicodedata.combining(ch)
    )
    return current


def _sanitize_payload_texts(payload: Any) -> Any:
    if isinstance(payload, str):
        return _fix_mojibake_text(payload)
    if isinstance(payload, list):
        return [_sanitize_payload_texts(item) for item in payload]
    if isinstance(payload, tuple):
        return tuple(_sanitize_payload_texts(item) for item in payload)
    if isinstance(payload, dict):
        return {k: _sanitize_payload_texts(v) for k, v in payload.items()}
    return payload


def _sanitize_control_texts(root: Optional[object], deep: bool = False) -> None:
    if root is None:
        return

    visited = set()
    text_attrs = ("value", "text", "label", "hint_text", "tooltip", "error_text", "helper_text")
    child_attrs = ("content", "title", "subtitle", "leading", "trailing")
    list_attrs = ("controls", "actions", "tabs", "destinations")
    generic_skip = set(text_attrs + child_attrs + list_attrs)

    def _walk(node: Optional[object]) -> None:
        if node is None:
            return
        nid = id(node)
        if nid in visited:
            return
        visited.add(nid)

        for attr in text_attrs:
            if not hasattr(node, attr):
                continue
            try:
                current = getattr(node, attr)
            except Exception:
                continue
            if isinstance(current, str):
                fixed = _fix_mojibake_text(current)
                if fixed != current:
                    try:
                        setattr(node, attr, fixed)
                    except Exception:
                        pass

        # Guard rail para erro WrapParentData/FlexParentData:
        # aplicamos apenas em modo deep (recuperacao de erro), para nao quebrar responsividade.
        if deep:
            try:
                if isinstance(node, ft.Row) and bool(getattr(node, "wrap", False)):
                    row_controls = getattr(node, "controls", None)
                    if isinstance(row_controls, (list, tuple)):
                        for child in row_controls:
                            if hasattr(child, "expand") and bool(getattr(child, "expand", False)):
                                try:
                                    setattr(child, "expand", False)
                                except Exception:
                                    pass
                    try:
                        setattr(node, "wrap", False)
                    except Exception:
                        pass
                    try:
                        if getattr(node, "scroll", None) is None:
                            setattr(node, "scroll", ft.ScrollMode.AUTO)
                    except Exception:
                        pass
            except Exception:
                pass

        for attr in child_attrs:
            if not hasattr(node, attr):
                continue
            try:
                child = getattr(node, attr)
            except Exception:
                continue
            if isinstance(child, str):
                fixed = _fix_mojibake_text(child)
                if fixed != child:
                    try:
                        setattr(node, attr, fixed)
                    except Exception:
                        pass
            else:
                _walk(child)

        for attr in list_attrs:
            if not hasattr(node, attr):
                continue
            try:
                items = getattr(node, attr)
            except Exception:
                continue
            if isinstance(items, (list, tuple)):
                for item in items:
                    _walk(item)

        if deep:
            # Fallback generico: percorre atributos de controles nao cobertos acima.
            try:
                node_vars = vars(node)
            except Exception:
                node_vars = {}
            for attr, value in node_vars.items():
                if attr.startswith("_") or attr in generic_skip:
                    continue
                if isinstance(value, ft.Control):
                    _walk(value)
                elif isinstance(value, (list, tuple, set)):
                    for item in value:
                        if isinstance(item, ft.Control):
                            _walk(item)
                elif isinstance(value, dict):
                    for item in value.values():
                        if isinstance(item, ft.Control):
                            _walk(item)

    _walk(root)


def _sanitize_page_controls(page: Optional[ft.Page]) -> None:
    if page is None:
        return
    try:
        for view in list(getattr(page, "views", []) or []):
            _sanitize_control_texts(view, deep=True)
        dialog = getattr(page, "dialog", None)
        if dialog is not None:
            _sanitize_control_texts(dialog, deep=True)
        bottom_sheet = getattr(page, "bottom_sheet", None)
        if bottom_sheet is not None:
            _sanitize_control_texts(bottom_sheet, deep=True)
        snack_bar = getattr(page, "snack_bar", None)
        if snack_bar is not None:
            _sanitize_control_texts(snack_bar, deep=True)
        for overlay in list(getattr(page, "overlay", []) or []):
            _sanitize_control_texts(overlay, deep=True)
    except Exception:
        pass


def _debug_scan_wrap_conflicts(root: Optional[object]) -> str:
    """Coleta uma fotografia rápida de Rows com wrap=True e filhos com expand=True."""
    if root is None:
        return ""
    seen = set()
    rows = []

    def _walk(node: Optional[object]):
        if node is None:
            return
        nid = id(node)
        if nid in seen:
            return
        seen.add(nid)
        try:
            if isinstance(node, ft.Row) and bool(getattr(node, "wrap", False)):
                bad = []
                ctrls = getattr(node, "controls", None)
                if isinstance(ctrls, list):
                    for idx, ch in enumerate(ctrls):
                        try:
                            bad.append((idx, ch.__class__.__name__, bool(getattr(ch, "expand", False))))
                        except Exception:
                            bad.append((idx, type(ch).__name__, False))
                rows.append(bad)
        except Exception:
            pass
        for attr in ("content", "leading", "trailing", "title", "subtitle"):
            child = getattr(node, attr, None)
            if child is not None and not isinstance(child, str):
                _walk(child)
        for attr in ("controls", "actions", "tabs", "destinations"):
            items = getattr(node, attr, None)
            if isinstance(items, list):
                for item in items:
                    if item is not None and not isinstance(item, str):
                        _walk(item)

    _walk(root)
    if not rows:
        return "wrap_rows=0"
    parts = [f"wrap_rows={len(rows)}"]
    for i, r in enumerate(rows):
        parts.append(f"row[{i}] children={r}")
    return " | ".join(parts)

def _create_user_ai_service(usuario: dict, force_economic: bool = False) -> Optional[AIService]:
    if not usuario:
        return None
    api_key = (usuario.get("api_key") or "").strip()
    if not api_key:
        return None
    provider_type = (usuario.get("provider") or "gemini").lower()
    provider_config = AI_PROVIDERS.get(provider_type, AI_PROVIDERS["gemini"])
    model_value = usuario.get("model") or provider_config.get("default_model")
    economia_mode = bool(usuario.get("economia_mode"))
    if economia_mode or force_economic:
        if provider_type == "gemini":
            model_value = "gemini-2.5-flash-lite"
        elif provider_type == "openai":
            model_value = "gpt-5-nano"
    anon_raw = str(usuario.get("id") or usuario.get("email") or "anon")
    user_anon = hashlib.sha256(anon_raw.encode("utf-8", errors="ignore")).hexdigest()[:16]
    telemetry_opt_in = bool(usuario.get("telemetry_opt_in"))
    try:
        return AIService(
            create_ai_provider(provider_type, api_key, model_value),
            telemetry_opt_in=telemetry_opt_in,
            user_anon=user_anon,
        )
    except Exception as ex:
        log_exception(ex, "main._create_user_ai_service")
        return None


def _emit_opt_in_event(
    usuario: Optional[dict],
    event_name: str,
    feature_name: str,
    latency_ms: int = 0,
    error_code: str = "",
):
    if not usuario or not bool(usuario.get("telemetry_opt_in")):
        return
    anon_raw = str(usuario.get("id") or usuario.get("email") or "anon")
    payload = {
        "timestamp": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "feature_name": str(feature_name or "app"),
        "provider": str(usuario.get("provider") or ""),
        "model": str(usuario.get("model") or ""),
        "latency_ms": int(max(0, latency_ms or 0)),
        "error_code": str(error_code or ""),
        "user_anon": hashlib.sha256(anon_raw.encode("utf-8", errors="ignore")).hexdigest()[:16],
    }
    try:
        log_event(event_name, json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass


def _build_focus_header(title: str, flow: str, etapa_control: ft.Control, dark: bool):
    return ft.Container(
        padding=ft.padding.only(bottom=4),
        content=ft.Column(
            [
                ft.Text(title, size=28, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                ft.Text(flow, size=14, color=_color("texto_sec", dark)),
                etapa_control,
            ],
            spacing=4,
        ),
    )


def _is_ai_quota_exceeded(service: Optional[AIService]) -> bool:
    if not service:
        return False
    provider = getattr(service, "provider", None)
    kind = str(getattr(provider, "last_error_kind", "") or "").lower()
    if kind in {"quota_hard", "quota_soft"}:
        return True
    msg = str(getattr(provider, "last_error_message", "") or "").lower()
    return ("quota exceeded" in msg) or ("429" in msg) or ("rate limit" in msg)


def _show_dialog_compat(page: Optional[ft.Page], dialog: ft.AlertDialog):
    if not page:
        return
    # Flet 0.80+ API
    if hasattr(page, "show_dialog"):
        page.show_dialog(dialog)
        return
    # Legacy fallback
    if hasattr(page, "open"):
        page.open(dialog)
        return
    # Last-resort fallback for older runtimes
    try:
        page.dialog = dialog
        dialog.open = True
        page.update()
    except Exception:
        pass


def _close_dialog_compat(page: Optional[ft.Page], dialog: Optional[ft.AlertDialog] = None):
    if not page:
        return
    # Flet 0.80+ API
    if hasattr(page, "pop_dialog"):
        try:
            page.pop_dialog()
            return
        except Exception:
            pass
    # Legacy fallback
    if dialog is not None and hasattr(page, "close"):
        try:
            page.close(dialog)
            return
        except Exception:
            pass
    # Last-resort fallback
    if dialog is not None:
        try:
            dialog.open = False
            page.update()
        except Exception:
            pass


def _launch_url_compat(page: Optional[ft.Page], url: str, ctx: str = "launch_url"):
    if not page:
        return
    link = str(url or "").strip()
    if not link:
        return
    try:
        result = page.launch_url(link)
        if asyncio.iscoroutine(result):
            async def _await_result():
                try:
                    await result
                except Exception as ex:
                    log_exception(ex, f"{ctx}.await")
            page.run_task(_await_result)
    except Exception as ex:
        log_exception(ex, ctx)


def _show_quota_dialog(page: Optional[ft.Page], navigate):
    if not page:
        return
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Cota da IA esgotada"),
        content=ft.Text(
            "As cotas atuais da API acabaram. Voce prefere inserir uma nova API key "
            "ou mudar o modelo/provedor (Gemini/GPT)?"
        ),
    )

    def _to_settings(_):
        _close_dialog_compat(page, dialog)
        navigate("/settings")

    def _continue_offline(_):
        _close_dialog_compat(page, dialog)

    dialog.actions = [
        ft.TextButton("Continuar offline", on_click=_continue_offline),
        ft.TextButton("Inserir nova API", on_click=_to_settings),
        ft.ElevatedButton("Mudar modelo (Gemini/GPT)", on_click=_to_settings),
    ]
    dialog.actions_alignment = ft.MainAxisAlignment.END
    _show_dialog_compat(page, dialog)


def _is_premium_active(usuario: dict) -> bool:
    return bool(usuario and int(usuario.get("premium_active") or 0) == 1)


def _backend_user_id(usuario: dict) -> int:
    try:
        return int(usuario.get("backend_user_id") or usuario.get("id") or 0)
    except Exception:
        return int(usuario.get("id") or 0)


def _generation_profile(usuario: dict, feature_key: str) -> dict:
    if _is_premium_active(usuario):
        return {"force_economic": False, "delay_s": 0.0, "label": "premium"}
    if feature_key in {"quiz", "flashcards"}:
        return {"force_economic": True, "delay_s": 0.0, "label": "free_fast"}
    return {"force_economic": False, "delay_s": 0.0, "label": "free"}


def _show_upgrade_dialog(page: Optional[ft.Page], navigate, message: str):
    if not page:
        return
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Recurso Premium"),
        content=ft.Text(message),
    )

    def _go_plans(_):
        _close_dialog_compat(page, dialog)
        navigate("/plans")

    dialog.actions = [
        ft.TextButton("Depois", on_click=lambda _: _close_dialog_compat(page, dialog)),
        ft.ElevatedButton("Ver planos", on_click=_go_plans),
    ]
    dialog.actions_alignment = ft.MainAxisAlignment.END
    _show_dialog_compat(page, dialog)


def _set_feedback_text(control: ft.Text, message: str, tone: str = "info"):
    palette = {
        "info": CORES.get("texto_sec", "#6B7280"),
        "success": CORES.get("sucesso", "#10B981"),
        "warning": CORES.get("warning", "#F59E0B"),
        "error": CORES.get("erro", "#EF4444"),
    }
    control.value = _fix_mojibake_text(str(message or ""))
    control.color = palette.get(tone, palette["info"])


def _wrap_study_content(content: ft.Control, dark: bool):
    return ft.Container(
        expand=True,
        bgcolor=_color("fundo", dark),
        padding=12,
        alignment=ft.Alignment(0, -1),
        content=content,
    )


def _status_banner(control: ft.Text, dark: bool):
    return ft.Container(
        bgcolor=ft.Colors.with_opacity(0.06, _color("texto", dark)),
        border_radius=8,
        padding=10,
        content=control,
    )


def _soft_border(dark: bool, alpha: float = 0.10):
    return ft.Colors.with_opacity(alpha, _color("texto", dark))


def _style_form_controls(control: ft.Control, dark: bool):
    if control is None:
        return
    try:
        if isinstance(control, ft.TextField):
            control.filled = True
            control.fill_color = ft.Colors.with_opacity(0.05, _color("texto", dark))
            control.border_color = _soft_border(dark, 0.12)
            control.focused_border_color = CORES["primaria"]
            control.border_radius = 12
            if getattr(control, "text_size", None) is None:
                control.text_size = 15
        elif isinstance(control, ft.Dropdown):
            control.filled = True
            control.fill_color = ft.Colors.with_opacity(0.05, _color("texto", dark))
            control.border_color = _soft_border(dark, 0.12)
            control.focused_border_color = CORES["primaria"]
            control.border_radius = 12
            if getattr(control, "text_size", None) is None:
                control.text_size = 15
        elif isinstance(control, ft.Switch):
            control.active_color = CORES["primaria"]
            control.inactive_track_color = _soft_border(dark, 0.20)
            control.inactive_thumb_color = _soft_border(dark, 0.45)
    except Exception:
        pass

    for child_attr in ("controls", "content", "leading", "title", "subtitle", "trailing"):
        if not hasattr(control, child_attr):
            continue
        child = getattr(control, child_attr)
        if child is None:
            continue
        if isinstance(child, list):
            for item in child:
                _style_form_controls(item, dark)
        else:
            _style_form_controls(child, dark)


def _apply_global_theme(page: ft.Page):
    page.theme = ft.Theme(
        use_material3=True,
        color_scheme_seed=CORES["primaria"],
        card_bgcolor=CORES["card"],
        scaffold_bgcolor=CORES["fundo"],
        divider_color=ft.Colors.with_opacity(0.08, CORES["texto"]),
    )
    page.dark_theme = ft.Theme(
        use_material3=True,
        color_scheme_seed=CORES["texto_sec_escuro"],
        card_bgcolor=CORES["card_escuro"],
        scaffold_bgcolor=CORES["fundo_escuro"],
        divider_color=ft.Colors.with_opacity(0.10, CORES["texto_escuro"]),
    )


def _logo_control(dark: bool):
    logo_path = os.path.join("assets", "logo_quizvance.png")
    if os.path.exists(logo_path):
        return ft.Image(src=logo_path, width=220, height=220, fit="contain"), True
    return ft.Text("Quiz Vance", size=32, weight=ft.FontWeight.BOLD, color=_color("texto", dark)), False

def _logo_small(dark: bool):
    logo_path = os.path.join("assets", "logo_quizvance.png")
    if os.path.exists(logo_path):
        return ft.Image(src=logo_path, width=110, height=110, fit="contain")
    return ft.Text("Quiz Vance", size=18, weight=ft.FontWeight.BOLD, color=_color("texto", dark))


def _read_uploaded_study_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except Exception as ex:
            log_exception(ex, "main._read_uploaded_study_text.import_pdf")
            return ""
        try:
            reader = PdfReader(file_path)
            pages = []
            for page_obj in reader.pages[:20]:
                pages.append((page_obj.extract_text() or "").strip())
            return "\n".join([p for p in pages if p])[:24000]
        except Exception as ex:
            log_exception(ex, "main._read_uploaded_study_text.read_pdf")
            return ""

    if ext in {".txt", ".md", ".csv", ".json", ".log"}:
        for encoding in ("utf-8", "latin-1"):
            try:
                with open(file_path, "r", encoding=encoding, errors="ignore") as f:
                    return (f.read() or "").strip()[:24000]
            except Exception:
                continue
    return ""


def _start_prioritized_session(state: dict, navigate):
    user = state.get("usuario") or {}
    db = state.get("db")
    if not db or not user.get("id"):
        navigate("/quiz")
        return
    try:
        preset = db.sugerir_estudo_agora(user["id"])
        state["quiz_preset"] = preset
        navigate("/quiz")
    except Exception as ex:
        log_exception(ex, "main._start_prioritized_session")
        navigate("/quiz")


def _pick_study_files_native() -> list[str]:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as ex:
        log_exception(ex, "main._pick_study_files_native.import")
        return []

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askopenfilenames(
            title="Selecione material para estudo",
            filetypes=[
                ("Documentos", "*.pdf *.txt *.md"),
                ("PDF", "*.pdf"),
                ("Texto", "*.txt"),
                ("Markdown", "*.md"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        return list(selected or [])
    except Exception as ex:
        log_exception(ex, "main._pick_study_files_native.dialog")
        return []
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def _get_or_create_file_picker(page: ft.Page) -> Optional[ft.FilePicker]:
    if not hasattr(ft, "FilePicker"):
        return None

    picker = getattr(page, "_quizvance_file_picker", None)
    if picker is not None:
        # garante que continua acoplado ao overlay
        if picker not in getattr(page, "overlay", []):
            page.overlay.append(picker)
            try:
                page.update()
            except Exception:
                pass
        return picker

    try:
        if not getattr(page, "overlay", None):
            try:
                page.overlay.clear()
            except Exception:
                pass
        picker = ft.FilePicker()
        page.overlay.append(picker)
        setattr(page, "_quizvance_file_picker", picker)
        page.update()
        return picker
    except Exception as ex:
        log_exception(ex, "main._get_or_create_file_picker")
        return None


async def _pick_study_files(page: Optional[ft.Page]) -> list[str]:
    if not page:
        return []

    picker = _get_or_create_file_picker(page)
    if picker is None:
        return await asyncio.to_thread(_pick_study_files_native)

    loop = asyncio.get_running_loop()
    result_future: asyncio.Future[list[str]] = loop.create_future()
    previous_handler = getattr(picker, "on_result", None)

    def _on_result(e):
        try:
            files = getattr(e, "files", None) or []
            selected_paths = []
            for file_obj in files:
                path = getattr(file_obj, "path", None)
                if path:
                    selected_paths.append(path)
            if not result_future.done():
                result_future.set_result(selected_paths)
        except Exception as ex_inner:
            if not result_future.done():
                result_future.set_exception(ex_inner)

    try:
        picker.on_result = _on_result
        try:
            picker.pick_files(
                allow_multiple=True,
                file_type=ft.FilePickerFileType.ANY,
                allowed_extensions=["pdf", "txt", "md", "csv", "json", "log"],
            )
        except Exception:
            # fallback generico
            try:
                picker.pick_files(allow_multiple=True)
            except Exception as ex:
                log_exception(ex, "main._pick_study_files.pick_files")
                return await asyncio.to_thread(_pick_study_files_native)

        try:
            selected = await asyncio.wait_for(result_future, timeout=240)
        except asyncio.TimeoutError:
            selected = []
        return selected
    except Exception as ex:
        log_exception(ex, "main._pick_study_files")
        return await asyncio.to_thread(_pick_study_files_native)
    finally:
        picker.on_result = previous_handler


def _extract_uploaded_material(file_paths: list[str]) -> tuple[list[str], list[str]]:
    upload_texts = []
    upload_names = []
    for file_path in file_paths:
        extracted = _read_uploaded_study_text(file_path)
        if extracted.strip():
            upload_texts.append(extracted)
            upload_names.append(os.path.basename(file_path))
    return upload_texts, upload_names


DEFAULT_QUIZ_QUESTIONS = [
    {
        "enunciado": "O que e aprendizagem espacada",
        "alternativas": [
            "Tecnica de revisar em intervalos crescentes",
            "Estudar tudo de uma vez",
            "Sempre repetir no mesmo intervalo",
            "Ler apenas uma vez",
        ],
        "correta_index": 0,
    },
    {
        "enunciado": "Qual comando git cria um novo branch",
        "alternativas": ["git branch <nome>", "git checkout -f", "git init", "git commit"],
        "correta_index": 0,
    },
    {
        "enunciado": "Em HTTP, qual codigo indica 'Nao Autorizado'",
        "alternativas": ["200", "301", "401", "500"],
        "correta_index": 2,
    },
    {
        "enunciado": "Qual linguagem Python usa para tipagem opcional",
        "alternativas": ["TypeScript", "mypy/typing", "Flow", "Kotlin"],
        "correta_index": 1,
    },
    {
        "enunciado": "Qual estrutura e usada para filas FIFO",
        "alternativas": ["stack", "queue", "tree", "set"],
        "correta_index": 1,
    },
]


def _build_sidebar(current_route: str, navigate, dark: bool, screen_w: float = 1280, collapsed: bool = False):
    items = []
    for route, label, icon in APP_ROUTES:
        selected = route == current_route
        row_controls = [
            ft.Icon(icon, size=18, color=CORES["primaria"] if selected else _color("texto_sec", dark)),
        ]
        if not collapsed:
            row_controls.append(
                ft.Text(
                    label,
                    color=CORES["primaria"] if selected else _color("texto", dark),
                    weight=ft.FontWeight.BOLD if selected else ft.FontWeight.W_500,
                )
            )
        items.append(
            ft.TextButton(
                content=ft.Row(
                    row_controls,
                    spacing=0 if collapsed else 10,
                    alignment=ft.MainAxisAlignment.CENTER if collapsed else ft.MainAxisAlignment.START,
                ),
                tooltip=label if collapsed else None,
                width=56 if collapsed else None,
                on_click=lambda _, r=route: navigate(r),
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.with_opacity(0.10, CORES["primaria"]) if selected else "transparent",
                    shape=ft.RoundedRectangleBorder(radius=10),
                    padding=10 if collapsed else 12,
                ),
            )
        )

    sidebar_width = 84 if collapsed else (210 if screen_w < 1440 else 230)
    logo_height = 84 if collapsed else (120 if screen_w < 1280 else 150)
    logo_path = os.path.join("assets", "logo_quizvance.png")
    logo_content = (
        ft.Image(src=logo_path, width=44, height=44, fit="contain")
        if collapsed and os.path.exists(logo_path)
        else (
            ft.Icon(ft.Icons.SCHOOL, size=34, color=CORES["primaria"])
            if collapsed
            else (
                ft.Image(src=logo_path, width=160, height=86, fit="contain")
                if os.path.exists(logo_path)
                else ft.Text("Quiz Vance", size=30, weight=ft.FontWeight.BOLD, color=_color("texto", dark))
            )
        )
    )
    logo_top = ft.Container(
        height=logo_height,
        border=ft.border.only(bottom=ft.BorderSide(1, _soft_border(dark, 0.10))),
        alignment=ft.Alignment(0, 0),
        content=logo_content,
    )

    return ft.Container(
        width=sidebar_width,
        padding=0,
        bgcolor=_color("card", dark),
        border=ft.border.only(right=ft.BorderSide(1, _soft_border(dark, 0.10))),
        content=ft.Column(
            controls=[
                logo_top,
                ft.Container(
                    expand=True,
                    padding=10 if collapsed else 16,
                    content=ft.ListView(
                        controls=items,
                        spacing=6,
                        expand=True,
                    ),
                ),
            ],
            spacing=0,
            expand=True,
        ),
    )

def _screen_width(page: ft.Page) -> float:
    def _normalize_mobile_dimension(raw_value: float) -> float:
        value = float(raw_value or 0.0)
        if value <= 0:
            return value
        page_platform = str(getattr(page, "platform", "") or "").lower()
        mobile_runtime = bool(is_android() or ("android" in page_platform) or ("ios" in page_platform))
        if not mobile_runtime:
            return value
        dpr_value = 0.0
        media = getattr(page, "media", None)
        if media is not None:
            try:
                dpr_value = float(getattr(media, "device_pixel_ratio", 0.0) or 0.0)
            except Exception:
                dpr_value = 0.0
        if dpr_value <= 0:
            try:
                dpr_value = float(getattr(page, "device_pixel_ratio", 0.0) or 0.0)
            except Exception:
                dpr_value = 0.0
        # Em muitos runtimes Flutter/Flet a largura ja vem em dp; so normaliza
        # quando o valor esta claramente em pixels fisicos.
        if dpr_value > 1.1 and value > 760:
            value = value / dpr_value
        elif value > 900:
            # Heuristica para devices que reportam largura fisica em pixels.
            value = value / 2.5
        return max(240.0, value)

    width = getattr(page, "width", None)
    if width:
        try:
            width_value = float(width)
            if width_value > 0:
                return _normalize_mobile_dimension(width_value)
        except Exception:
            pass

    window_width = getattr(page, "window_width", None)
    if window_width:
        try:
            window_value = float(window_width)
            if window_value > 0:
                return _normalize_mobile_dimension(window_value)
        except Exception:
            pass

    return 1280.0


def _screen_height(page: ft.Page) -> float:
    def _normalize_mobile_dimension(raw_value: float) -> float:
        value = float(raw_value or 0.0)
        if value <= 0:
            return value
        page_platform = str(getattr(page, "platform", "") or "").lower()
        mobile_runtime = bool(is_android() or ("android" in page_platform) or ("ios" in page_platform))
        if not mobile_runtime:
            return value
        dpr_value = 0.0
        media = getattr(page, "media", None)
        if media is not None:
            try:
                dpr_value = float(getattr(media, "device_pixel_ratio", 0.0) or 0.0)
            except Exception:
                dpr_value = 0.0
        if dpr_value <= 0:
            try:
                dpr_value = float(getattr(page, "device_pixel_ratio", 0.0) or 0.0)
            except Exception:
                dpr_value = 0.0
        # Altura em dp nao deve ser reescalada; normaliza apenas se vier fisica.
        if dpr_value > 1.1 and value > 1280:
            value = value / dpr_value
        elif value > 1400:
            value = value / 2.5
        return max(360.0, value)

    height = getattr(page, "height", None)
    if height:
        try:
            height_value = float(height)
            if height_value > 0:
                return _normalize_mobile_dimension(height_value)
        except Exception:
            pass

    window_height = getattr(page, "window_height", None)
    if window_height:
        try:
            window_value = float(window_height)
            if window_value > 0:
                return _normalize_mobile_dimension(window_value)
        except Exception:
            pass

    return 820.0


def _format_datetime_label(value: Optional[str]) -> str:
    if not value:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    try:
        dt_iso = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt_iso.strftime("%d/%m/%Y %H:%M")
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.datetime.strptime(raw, fmt)
            return dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            continue
    return raw


def _format_exam_date_input(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())[:8]
    if len(digits) <= 2:
        return digits
    if len(digits) <= 4:
        return f"{digits[:2]}/{digits[2:]}"
    return f"{digits[:2]}/{digits[2:4]}/{digits[4:]}"


def _parse_br_date(value: str) -> Optional[datetime.date]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.datetime.strptime(raw, "%d/%m/%Y").date()
    except Exception:
        return None


def _build_compact_nav(current_route: str, navigate, dark: bool):
    buttons = []
    for route, label, icon in APP_ROUTES:
        selected = route == current_route
        buttons.append(
            ft.TextButton(
                content=ft.Row(
                    [
                        ft.Icon(icon, size=16, color=CORES["primaria"] if selected else _color("texto_sec", dark)),
                        ft.Text(
                            label,
                            size=12,
                            color=CORES["primaria"] if selected else _color("texto", dark),
                            weight=ft.FontWeight.BOLD if selected else ft.FontWeight.W_500,
                        ),
                    ],
                    spacing=6,
                ),
                on_click=lambda _, r=route: navigate(r),
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.with_opacity(0.10, CORES["primaria"]) if selected else "transparent",
                    shape=ft.RoundedRectangleBorder(radius=8),
                    padding=ft.Padding(10, 8, 10, 8),
                ),
            )
        )

    return ft.Container(
        bgcolor=_color("card", dark),
        border=ft.border.only(bottom=ft.BorderSide(1, _soft_border(dark, 0.10))),
        padding=ft.padding.symmetric(horizontal=8, vertical=6),
        content=ft.Row(
            controls=buttons,
            spacing=6,
            scroll=ft.ScrollMode.AUTO,
        ),
    )


def _build_home_body(state: dict, navigate, dark: bool):
    usuario = state.get("usuario") or {}
    db = state.get("db")
    nome = usuario.get("nome", "Usuario")

    # ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ Dados do progresso ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬
    progresso = {
        "meta_questoes": int(usuario.get("meta_questoes_diaria") or 20),
        "questoes_respondidas": 0,
        "acertos": 0,
        "progresso_meta": 0.0,
        "streak_dias": int(usuario.get("streak_dias") or 0),
        "pct_acerto_7d": 0.0,
        "pct_acerto_30d": 0.0,
        "revisoes_pendentes": 0,
        "ultima_sessao_rota": None,
        "ultima_sessao_label": None,
    }
    if db and usuario.get("id"):
        try:
            pd = db.obter_progresso_diario(usuario["id"])
            if pd:
                progresso.update(pd)
            rev = db.revisoes_pendentes(usuario["id"])
            progresso["revisoes_pendentes"] = int(rev or 0)
        except Exception as ex:
            log_exception(ex, "home.progresso_diario")

    streak = int(progresso.get("streak_dias") or 0)
    respondidas = int(progresso.get("questoes_respondidas") or 0)
    meta = int(progresso.get("meta_questoes") or 20)
    acertos = int(progresso.get("acertos") or 0)
    pct_acerto = round((acertos / respondidas * 100) if respondidas > 0 else 0)
    revisoes_pend = int(progresso.get("revisoes_pendentes") or 0)
    progresso_meta = min(1.0, respondidas / max(meta, 1))

    # ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ SaudaÃƒÆ’Ã‚Â§ÃƒÆ’Ã‚Â£o ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬
    hora = datetime.datetime.now().hour
    if hora < 12:
        saudacao_label = "Bom dia"
    elif hora < 18:
        saudacao_label = "Boa tarde"
    else:
        saudacao_label = "Boa noite"

    streak_emoji = "🔥" if streak > 0 else "💪"
    streak_text = f"{streak} dia{'s' if streak != 1 else ''} de sequencia" if streak > 0 else "Comece sua sequencia hoje!"

    saudacao = ft.Column(
        [
            ft.Text(f"{saudacao_label}, {nome.split()[0]}!", size=DS.FS_H2, weight=DS.FW_BOLD, color=DS.text_color(dark)),
            ft.Row(
                [
                    ft.Text(streak_emoji, size=18),
                    ft.Text(streak_text, size=DS.FS_BODY_S, color=DS.text_sec_color(dark)),
                ],
                spacing=DS.SP_4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        spacing=DS.SP_4,
    )

    # ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ Stat cards ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬
    stat_cards = [
        ds_stat_card(
            col={"xs": 6, "sm": 6, "md": 3},
            height=172,
            icon=ft.Icons.TODAY_OUTLINED,
            label="Questoes hoje",
            value=f"{respondidas}/{meta}",
            subtitle=f"{int(progresso_meta*100)}% da meta",
            dark=dark,
            icon_color=DS.P_500,
            on_click=lambda _: navigate("/quiz"),
        ),
        ds_stat_card(
            col={"xs": 6, "sm": 6, "md": 3},
            height=172,
            icon=ft.Icons.TRACK_CHANGES_OUTLINED,
            label="% Acerto (hoje)",
            value=f"{pct_acerto}%",
            subtitle=f"{acertos} de {respondidas} certas",
            dark=dark,
            icon_color=DS.SUCESSO if pct_acerto >= 70 else DS.WARNING,
            trend_up=pct_acerto >= 70 if respondidas > 0 else None,
        ),
        ds_stat_card(
            col={"xs": 6, "sm": 6, "md": 3},
            height=172,
            icon=ft.Icons.REPLAY_OUTLINED,
            label="Revisoes pendentes",
            value=str(revisoes_pend),
            subtitle="Clique para revisar",
            dark=dark,
            icon_color=DS.ERRO if revisoes_pend > 5 else DS.A_500,
            on_click=lambda _: navigate("/revisao"),
        ),
        ds_stat_card(
            col={"xs": 6, "sm": 6, "md": 3},
            height=172,
            icon=ft.Icons.LOCAL_FIRE_DEPARTMENT_OUTLINED,
            label="Sequencia",
            value=f"{streak}" if streak > 0 else "0",
            subtitle="dias consecutivos",
            dark=dark,
            icon_color=DS.WARNING,
        ),
    ]

    # ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ Meta diÃƒÆ’Ã‚Â¡ria com barra de progresso ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬
    meta_card = ds_card(
        dark=dark,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Meta Diaria", size=DS.FS_BODY, weight=DS.FW_SEMI, color=DS.text_color(dark)),
                        ft.Text(f"{respondidas}/{meta} questoes", size=DS.FS_CAPTION, color=DS.text_sec_color(dark)),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ds_progress_bar(progresso_meta, dark=dark, height=10, color=DS.P_500),
                ft.Row(
                    [
                        ds_btn_primary(
                            "Continuar estudando" if respondidas > 0 else "Comecar agora",
                            on_click=lambda _: navigate("/quiz"),
                            icon=ft.Icons.PLAY_ARROW_ROUNDED,
                            dark=dark,
                            height=44,
                            expand=True,
                        ),
                        ds_btn_secondary(
                            "Ver revisoes",
                            on_click=lambda _: navigate("/revisao"),
                            icon=ft.Icons.REPLAY_OUTLINED,
                            dark=dark,
                            height=44,
                            expand=True,
                        ) if revisoes_pend > 0 else ft.Container(expand=True, visible=False),
                    ],
                    wrap=True,
                    spacing=DS.SP_12,
                ),
            ],
            spacing=DS.SP_12,
        ),
    )

    # ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ Card: Estudar um tema (stub para Commit 8) ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬
    # Campo de tema inline - funcional (Commit 8)
    tema_input = ft.TextField(
        hint_text="Ex.: Direito Constitucional, Calculo I",
        border_radius=DS.R_MD,
        expand=True,
        dense=True,
        on_submit=lambda e: _iniciar_tema(e.control.value),
    )

    def _iniciar_tema(tema_valor: str = None):
        tema = (tema_valor or tema_input.value or "").strip()
        if not tema:
            return
        state["quiz_preset"] = {"topic": tema, "count": "10", "difficulty": "intermediario"}
        navigate("/quiz")

    tema_card = ds_card(
        dark=dark,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(ft.Icons.AUTO_AWESOME, size=22, color=DS.P_500),
                            bgcolor=f"{DS.P_500}1A",
                            border_radius=DS.R_MD,
                            padding=DS.SP_12,
                        ),
                        ft.Column(
                            [
                                ft.Text("Estudar um tema com IA", size=DS.FS_BODY, weight=DS.FW_SEMI, color=DS.text_color(dark)),
                                ft.Text("Gere questoes personalizadas em segundos", size=DS.FS_CAPTION, color=DS.text_sec_color(dark)),
                            ],
                            spacing=DS.SP_4,
                            expand=True,
                        ),
                    ],
                    spacing=DS.SP_12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [
                        tema_input,
                        ds_btn_primary(
                            "Gerar",
                            on_click=lambda _: _iniciar_tema(),
                            icon=ft.Icons.ARROW_FORWARD_ROUNDED,
                            dark=dark,
                            height=DS.TAP_MIN,
                        ),
                    ],
                    wrap=True,
                    spacing=DS.SP_8,
                ),
            ],
            spacing=DS.SP_12,
        ),
        border_color=DS.P_300 if not dark else DS.P_900,
    )

    return ft.Container(
        expand=True,
        content=ft.Column(
            [
                saudacao,
                ft.Container(height=DS.SP_4),
                ft.ResponsiveRow(controls=stat_cards, columns=12, spacing=DS.SP_12, run_spacing=DS.SP_12),
                meta_card,
                tema_card,
                ft.Container(height=DS.SP_32),
            ],
            spacing=DS.SP_16,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        ),
        padding=DS.SP_16,
    )



def _build_onboarding_body(state: dict, navigate, dark: bool):
    page = state.get("page")
    user = state.get("usuario") or {}
    db = state.get("db")
    screen_w = _screen_width(page) if page else 1280
    compact = screen_w < 960
    mobile = screen_w < 760
    needs_setup = (not user.get("oauth_google")) and (not (user.get("api_key") or "").strip())

    plan_code = str(user.get("plan_code") or "free").lower()
    premium_active = bool(int(user.get("premium_active") or 0))
    premium_until = _format_datetime_label(user.get("premium_until"))
    trial_active = plan_code == "trial" and premium_active

    status_text = ft.Text("", size=12, color=_color("texto_sec", dark))

    def finish_onboarding(_):
        try:
            uid = user.get("id")
            if uid and db:
                db.marcar_onboarding_visto(int(uid))
            if uid and state.get("usuario"):
                state["usuario"]["onboarding_seen"] = 1
            if needs_setup:
                navigate("/settings")
            else:
                navigate("/home")
        except Exception as ex:
            log_exception(ex, "main.finish_onboarding")
            status_text.value = "Falha ao concluir boas-vindas. Tente novamente."
            status_text.color = CORES["erro"]
            if page:
                page.update()

    def _feature_line(text: str):
        return ft.Row(
            [
                ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color=CORES["primaria"]),
                ft.Text(text, size=12, color=_color("texto_sec", dark), expand=True),
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    intro_card = ft.Card(
        elevation=1,
        content=ft.Container(
            padding=14 if mobile else 16,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.WAVING_HAND, color=CORES["primaria"], size=22),
                            ft.Text("Boas-vindas ao Quiz Vance", size=20 if mobile else 24, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                        ],
                        spacing=8,
                        wrap=True,
                    ),
                    ft.Text(
                        "Este guia rapido aparece apenas no primeiro login de contas novas.",
                        size=13,
                        color=_color("texto_sec", dark),
                    ),
                    ft.Container(height=2),
                    _feature_line("1) Escolha um modulo: Questoes, Flashcards, Biblioteca ou Dissertativo."),
                    _feature_line("2) Gere sua sessao de estudo com IA e acompanhe seu progresso."),
                    _feature_line("3) Use o menu para navegar e ajustar tema, perfil e configuracoes."),
                ],
                spacing=8,
            ),
        ),
    )

    free_card = ft.Card(
        elevation=1,
        content=ft.Container(
            padding=14,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.LOCK_OPEN, size=20, color=CORES["acento"]),
                            ft.Text("Conta Free", size=17, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                        ],
                        spacing=8,
                    ),
                    _feature_line("Questoes e flashcards com modo economico."),
                    _feature_line("Correcao de dissertativa: 1 por dia."),
                    _feature_line("Acesso completo ao painel e biblioteca."),
                ],
                spacing=8,
            ),
        ),
    )

    premium_card = ft.Card(
        elevation=1,
        content=ft.Container(
            padding=14,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.WORKSPACE_PREMIUM, size=20, color=CORES["primaria"]),
                            ft.Text("Conta Premium", size=17, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                        ],
                        spacing=8,
                    ),
                    _feature_line("Respostas mais rapidas e qualidade maxima dos modelos."),
                    _feature_line("Mais produtividade para sessoes longas."),
                    _feature_line("Melhor custo-beneficio para uso diario intenso."),
                ],
                spacing=8,
            ),
        ),
    )

    trial_title = "Cortesia ativa: 1 dia de Premium" if trial_active else "Cortesia de 1 dia para novos usuarios"
    trial_subtitle = (
        f"Seu periodo de cortesia vai ate {premium_until}."
        if premium_until
        else "A cortesia e aplicada automaticamente na criacao da conta."
    )
    if (not trial_active) and premium_until:
        trial_subtitle = f"Cortesia registrada ate {premium_until}. Veja os planos para continuar."

    trial_card = ft.Card(
        elevation=1,
        content=ft.Container(
            padding=14,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.CARD_GIFTCARD, size=20, color=CORES["warning"]),
                            ft.Text(trial_title, size=17, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                        ],
                        spacing=8,
                        wrap=True,
                    ),
                    ft.Text(trial_subtitle, size=13, color=_color("texto_sec", dark)),
                    ft.Row(
                        [
                            ft.ElevatedButton("Ver planos", icon=ft.Icons.STARS, on_click=lambda _: navigate("/plans")),
                            ft.OutlinedButton("Comecar agora", icon=ft.Icons.ARROW_FORWARD, on_click=finish_onboarding),
                        ],
                        spacing=10,
                        wrap=True,
                    ),
                    status_text,
                ],
                spacing=8,
            ),
        ),
    )

    config_hint = ft.Container()
    if needs_setup:
        config_hint = ft.Container(
            padding=10,
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.08, CORES["warning"]),
            content=ft.Text(
                "Antes de estudar com IA, configure provider, modelo e API key na tela de Configuracoes.",
                size=12,
                color=_color("texto", dark),
            ),
        )

    return ft.Container(
        expand=True,
        bgcolor=_color("fundo", dark),
        padding=12 if mobile else 18,
        content=ft.Column(
            [
                intro_card,
                ft.ResponsiveRow(
                    controls=[
                        ft.Container(col={"sm": 12, "md": 6}, content=free_card),
                        ft.Container(col={"sm": 12, "md": 6}, content=premium_card),
                    ],
                    spacing=10,
                    run_spacing=10,
                ),
                trial_card,
                config_hint,
            ],
            spacing=10 if compact else 12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        ),
    )


def _build_placeholder_body(title: str, description: str, navigate, dark: bool):
    tips = {
        "Questoes": [
            "Escolha categoria e dificuldade para gerar questoes.",
            "Cada rodada traz 5 questoes com feedback imediato.",
            "Use 'Reforco' para ver explicacoes detalhadas."
        ],
        "Flashcards": [
            "Selecione tema e gere baralho com IA.",
            "Marque como 'Lembrei' ou 'Rever' para espacamento.",
            "Exporte pacotes de estudo em Markdown pela Biblioteca."
        ],
        "Dissertativo": [
            "Digite a pergunta ou cole o enunciado.",
            "Receba estrutura de resposta, pontos-chave e referencia.",
            "Peca reescrita por clareza ou concisao."
        ],
        "Estatisticas": [
            "Painel mostra XP diario e taxa de acerto por tema.",
            "Ranking interno por XP acumulado.",
            "Filtros por periodo e categoria (coming soon)."
        ],
        "Perfil": [
            "Atualize nome, avatar e preferencia de tema.",
            "Configure provider/modelo de IA por default.",
            "Gerencie chaves de API de forma segura."
        ],
        "Ranking": [
            "Comparacao com outros usuarios por XP.",
            "Exibe nivel, taxa de acerto e horas de estudo.",
            "Resets semanais opcionais (beta)."
        ],
        "Conquistas": [
            "Desbloqueie medalhas por metas de estudo.",
            "Bonus de XP ao concluir marcos.",
            "Streaks diarias contam para conquistas especiais."
        ],
        "Configuracoes": [
            "Troque tema, idioma e notificacoes.",
            "Selecione provider/modelo principal.",
            "Backup e restauracao de dados (em breve)."
        ],
    }

    rows = [
        ft.ListTile(
            leading=ft.Icon(ft.Icons.CHEVRON_RIGHT, color=CORES["primaria"]),
            title=ft.Text(t, color=_color("texto", dark)),
        ) for t in tips.get(title, [description])
    ]

    return ft.Container(
        expand=True,
        bgcolor=_color("fundo", dark),
        padding=20,
        content=ft.Column(
            [
                ft.Text(title, size=28, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                ft.Text(description, size=14, color=_color("texto_sec", dark)),
                ft.Container(height=12),
                ft.Card(content=ft.Column(rows, spacing=0), elevation=2),
                ft.Container(height=16),
                ft.ElevatedButton("Voltar ao Inicio", on_click=lambda _: navigate("/home")),
            ],
            spacing=10,
        ),
    )



def _build_library_body(state, navigate, dark: bool):
    page = state.get("page")
    user = state.get("usuario") or {}
    db = state.get("db")
    if not db or not user:
        return ft.Text("Erro: Usuario nao autenticado")
        
    library_service = LibraryService(db)
    from core.services.study_summary_service import StudySummaryService
    summary_service = StudySummaryService()
    
    # Estado local
    file_list = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
    package_list = ft.Column(spacing=8)
    status_text = ft.Text("", size=12, color=_color("texto_sec", dark))
    upload_ring = ft.ProgressRing(width=20, height=20, visible=False)
    files_count_text = ft.Text("0", size=20, weight=ft.FontWeight.BOLD, color=_color("texto", dark))
    packs_count_text = ft.Text("0", size=20, weight=ft.FontWeight.BOLD, color=CORES["primaria"])

    def _start_quiz_from_package(dados: dict):
        questions = dados.get("questoes") or []
        if not questions:
            status_text.value = "Pacote sem questoes."
            status_text.color = CORES["warning"]
            if page:
                page.update()
            return
        state["quiz_package_questions"] = questions
        navigate("/quiz")

    def _start_flashcards_from_package(dados: dict):
        cards = dados.get("flashcards") or []
        if not cards:
            summary = dados.get("summary_v2") or {}
            cards = summary.get("sugestoes_flashcards") or []
        seed_cards = []
        for item in cards:
            if not isinstance(item, dict):
                continue
            frente = str(item.get("frente") or item.get("front") or "").strip()
            verso = str(item.get("verso") or item.get("back") or "").strip()
            if frente and verso:
                seed_cards.append({"frente": frente, "verso": verso})
        if not seed_cards:
            status_text.value = "Pacote sem flashcards."
            status_text.color = CORES["warning"]
            if page:
                page.update()
            return
        state["flashcards_seed_cards"] = seed_cards
        navigate("/flashcards")

    def _start_plan_from_package(pkg: dict):
        dados = pkg.get("dados") or {}
        summary = dados.get("summary_v2") or {}
        topicos = summary.get("topicos_principais") or summary.get("topicos") or dados.get("topicos") or []
        topicos = [str(t).strip() for t in topicos if str(t).strip()][:10]
        state["study_plan_seed"] = {
            "objetivo": str(pkg.get("titulo") or "Plano de estudo"),
            "data_prova": "",
            "tempo_diario": 90,
            "topicos": topicos,
        }
        navigate("/study-plan")

    def _safe_file_stub(value: str) -> str:
        return summary_service.safe_file_stub(value)

    def _build_package_markdown(pkg: dict) -> str:
        return summary_service.build_package_markdown(pkg)

    def _build_package_plain_text(pkg: dict) -> str:
        return summary_service.build_package_plain_text(pkg)

    def _write_simple_pdf(path, title: str, text: str):
        _ = title
        summary_service.write_simple_pdf(path, text)

    def _export_package_markdown(pkg: dict):
        try:
            export_dir = get_data_dir() / "exports"
            export_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            nome_base = _safe_file_stub(pkg.get("titulo") or "pacote_estudo")
            out_path = export_dir / f"{nome_base}_{stamp}.md"
            markdown = _build_package_markdown(pkg)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(markdown)
            status_text.value = f"Resumo exportado: {out_path}"
            status_text.color = CORES["sucesso"]
            if page:
                ds_toast(page, "Exportado em Markdown.", tipo="sucesso")
                page.update()
        except Exception as ex:
            log_exception(ex, "_export_package_markdown")
            status_text.value = "Falha ao exportar Markdown."
            status_text.color = CORES["erro"]
            if page:
                ds_toast(page, "Erro ao exportar Markdown.", tipo="erro")
                page.update()

    def _export_package_pdf(pkg: dict):
        try:
            export_dir = get_data_dir() / "exports"
            export_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            nome_base = _safe_file_stub(pkg.get("titulo") or "pacote_estudo")
            out_path = export_dir / f"{nome_base}_{stamp}.pdf"
            plain_text = _build_package_plain_text(pkg)
            _write_simple_pdf(out_path, str(pkg.get("titulo") or "Pacote de Estudo"), plain_text)
            status_text.value = f"PDF exportado: {out_path}"
            status_text.color = CORES["sucesso"]
            if page:
                ds_toast(page, "Exportado em PDF.", tipo="sucesso")
                page.update()
        except Exception as ex:
            log_exception(ex, "_export_package_pdf")
            status_text.value = "Falha ao exportar PDF."
            status_text.color = CORES["erro"]
            if page:
                ds_toast(page, "Erro ao exportar PDF.", tipo="erro")
                page.update()

    def _refresh_packages():
        package_list.controls.clear()
        try:
            packs = db.listar_study_packages(user["id"], limite=8)
        except Exception as ex:
            log_exception(ex, "_refresh_packages")
            packs = []
        packs_count_text.value = str(len(packs))
        if not packs:
            package_list.controls.append(
                ft.Text("Nenhum pacote gerado ainda.", size=12, color=_color("texto_sec", dark))
            )
            return
        for p in packs:
            dados = p.get("dados") or {}
            qcount = len(dados.get("questoes") or [])
            fcount = len(dados.get("flashcards") or [])
            package_list.controls.append(
                ft.Container(
                    padding=8,
                    border_radius=8,
                    bgcolor=_color("card", dark),
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Column(
                                        [
                                            ft.Text(p.get("titulo", "Pacote"), weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                            ft.Text(f"{qcount} questoes - {fcount} flashcards", size=12, color=_color("texto_sec", dark)),
                                        ],
                                        spacing=2,
                                        expand=True,
                                    ),
                                ],
                            ),
                            ft.Row(
                                [
                                    ft.TextButton(
                                        "Usar no Quiz",
                                        icon=ft.Icons.PLAY_ARROW,
                                        on_click=lambda _, d=dados: _start_quiz_from_package(d),
                                    ),
                                    ft.TextButton(
                                        "Flashcards",
                                        icon=ft.Icons.STYLE_OUTLINED,
                                        on_click=lambda _, d=dados: _start_flashcards_from_package(d),
                                    ),
                                    ft.TextButton(
                                        "Plano 7d",
                                        icon=ft.Icons.CALENDAR_MONTH_OUTLINED,
                                        on_click=lambda _, item=p: _start_plan_from_package(item),
                                    ),
                                    ft.TextButton(
                                        "Exportar MD",
                                        icon=ft.Icons.DOWNLOAD_OUTLINED,
                                        on_click=lambda _, p=p: _export_package_markdown(p),
                                    ),
                                    ft.TextButton(
                                        "Exportar PDF",
                                        icon=ft.Icons.PICTURE_AS_PDF,
                                        on_click=lambda _, p=p: _export_package_pdf(p),
                                    ),
                                ],
                                wrap=True,
                                spacing=6,
                            ),
                        ],
                        spacing=6,
                    ),
                )
            )

    async def _generate_package_async(file_id: int, file_name: str):
        if not page:
            return
        status_text.value = f"Gerando pacote: {file_name}..."
        status_text.color = _color("texto_sec", dark)
        upload_ring.visible = True
        page.update()
        try:
            content_txt = await asyncio.to_thread(library_service.get_conteudo_arquivo, file_id)
            if not content_txt.strip():
                status_text.value = "Arquivo sem texto para pacote."
                status_text.color = CORES["warning"]
                return
            chunks = [line.strip() for line in content_txt.splitlines() if line.strip()]
            source_hash = hashlib.sha256(
                f"{file_name}\n{content_txt[:180000]}".encode("utf-8", errors="ignore")
            ).hexdigest()
            service = _create_user_ai_service(user)
            summary = {
                "titulo": f"Resumo de {file_name}",
                "resumo_curto": "Resumo indisponivel.",
                "resumo_estruturado": [],
                "topicos_principais": [],
                "definicoes": [],
                "exemplos": [],
                "pegadinhas": [],
                "checklist_de_estudo": [],
                "sugestoes_flashcards": [],
                "sugestoes_questoes": [],
                "resumo": "Resumo indisponivel.",
                "topicos": [],
            }
            summary_from_cache = False
            if db and user.get("id"):
                cached = db.obter_resumo_por_hash(int(user["id"]), source_hash)
                if isinstance(cached, dict) and cached:
                    summary = cached
                    summary_from_cache = True
                    status_text.value = "Resumo reutilizado do cache. Gerando questoes..."
            questoes = []
            flashcards = []
            if service:
                if not summary_from_cache:
                    if (not _is_premium_active(user)) and db and user.get("id"):
                        allowed, _used = db.consumir_limite_diario(int(user["id"]), "study_summary", 2)
                        if not allowed:
                            status_text.value = "Plano Free: limite de 2 resumos/dia atingido."
                            status_text.color = CORES["warning"]
                            _show_upgrade_dialog(page, navigate, "No Premium voce gera resumos ilimitados por dia.")
                            return
                    summary = await asyncio.to_thread(service.generate_study_summary, chunks, file_name, 1)
                    if db and user.get("id"):
                        try:
                            db.salvar_resumo_por_hash(int(user["id"]), source_hash, file_name, summary)
                        except Exception as ex:
                            log_exception(ex, "_generate_package_async.save_summary_cache")
                lote_quiz = await asyncio.to_thread(
                    service.generate_quiz_batch,
                    chunks,
                    file_name,
                    "Intermediario",
                    3,
                    1,
                )
                for q in lote_quiz or []:
                    questoes.append(
                        _sanitize_payload_texts({
                            "enunciado": q.get("pergunta", ""),
                            "alternativas": q.get("opcoes", []),
                            "correta_index": q.get("correta_index", 0),
                        })
                    )
                flashcards = await asyncio.to_thread(service.generate_flashcards, chunks, 5, 1)
            if not questoes:
                questoes = random.sample(DEFAULT_QUIZ_QUESTIONS, min(3, len(DEFAULT_QUIZ_QUESTIONS)))
            if db and user.get("id"):
                try:
                    if flashcards:
                        db.salvar_flashcards_gerados(int(user["id"]), str(file_name or "Geral"), flashcards, "intermediario")
                    if questoes:
                        from core.repositories.question_progress_repository import QuestionProgressRepository
                        qrepo = QuestionProgressRepository(db)
                        for q in questoes:
                            if isinstance(q, dict):
                                qrepo.register_result(int(user["id"]), q, "mark")
                except Exception as ex:
                    log_exception(ex, "_generate_package_async.integrate_review_flow")
            resumo_curto = str(summary.get("resumo_curto") or summary.get("resumo") or "").strip()
            topicos_principais = summary.get("topicos_principais") or summary.get("topicos") or []
            if not isinstance(topicos_principais, list):
                topicos_principais = []
            pacote = {
                "resumo": resumo_curto,
                "topicos": [str(t).strip() for t in topicos_principais if str(t).strip()][:12],
                "summary_v2": summary,
                "questoes": questoes,
                "flashcards": flashcards,
            }
            db.salvar_study_package(user["id"], f"Pacote - {file_name}", file_name, pacote)
            status_text.value = "Pacote gerado e salvo."
            status_text.color = CORES["sucesso"]
            _refresh_packages()
        except Exception as ex:
            log_exception(ex, "_generate_package_async")
            msg = str(ex).lower()
            if "401" in msg or "key" in msg or "auth" in msg:
                 status_text.value = "Erro: API Key invalida!"
                 ds_toast(page, "Chave de API invalida. Verifique Configuracoes.", tipo="erro")
            elif "429" in msg or "quota" in msg:
                 status_text.value = "Erro: Cota excedida!"
                 ds_toast(page, "Limite gratuito da API excedido.", tipo="erro")
            else:
                 status_text.value = "Falha tecnica na geracao."
                 ds_toast(page, f"Erro na IA: {msg[:40]}...", tipo="erro")
            status_text.color = CORES["erro"]
        finally:
            upload_ring.visible = False
            page.update()

    def _refresh_list():
        try:
            file_list.controls.clear()
            arquivos = library_service.listar_arquivos(user["id"])
            log_event("library_refresh", f"found {len(arquivos)} files")
            files_count_text.value = str(len(arquivos))
            
            if not arquivos:
                file_list.controls.append(
                    ft.Container(
                        padding=20,
                        alignment=ft.Alignment(0, 0),
                        content=ft.Column([
                            ft.Icon(ft.Icons.LIBRARY_ADD, size=48, color=_color("texto_sec", dark)),
                            ft.Text("Sua biblioteca esta vazia", color=_color("texto_sec", dark)),
                            ft.Text("Faca upload de PDFs para usar nos quizzes", size=12, color=_color("texto_sec", dark))
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                    )
                )
            else:
                for arq in arquivos:
                    nome = arq["nome_arquivo"]
                    date_str = arq.get("data_upload", "")[:10]
                    fid = arq["id"]
                    
                    # Botao de excluir
                    btn_delete = ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE, 
                        icon_color=CORES["erro"],
                        tooltip="Excluir",
                        on_click=lambda _, i=fid: _delete_file(i)
                    )
                    btn_package = ft.TextButton(
                        "Gerar pacote",
                        icon=ft.Icons.AUTO_AWESOME,
                        on_click=lambda _, i=fid, n=nome: page.run_task(_generate_package_async, i, n),
                    )
                    
                    file_list.controls.append(
                        ft.Container(
                            padding=10,
                            border_radius=8,
                            bgcolor=_color("card", dark),
                            content=ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.Icon(ft.Icons.PICTURE_AS_PDF if nome.endswith(".pdf") else ft.Icons.DESCRIPTION, color=CORES["primaria"]),
                                            ft.Column([
                                                ft.Text(nome, weight=ft.FontWeight.BOLD, color=_color("texto", dark), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                                ft.Text(f"Adicionado em {date_str} - {arq.get('total_paginas', 0)} paginas", size=12, color=_color("texto_sec", dark))
                                            ], expand=True, spacing=2),
                                        ],
                                        spacing=8,
                                    ),
                                    ft.Row(
                                        [btn_package, btn_delete],
                                        wrap=True,
                                        spacing=6,
                                    ),
                                ],
                                spacing=6,
                            )
                        )
                    )
            
            if page: page.update()
        except Exception as e:
            log_exception(e, "_refresh_list")

    def _delete_file(file_id):
        try:
            library_service.excluir_arquivo(file_id, user["id"])
            status_text.value = "Arquivo removido."
            status_text.color = CORES["sucesso"]
            _refresh_list()
        except Exception as e:
            status_text.value = f"Erro: {e}"
            status_text.color = CORES["erro"]
            log_exception(e, "_delete_file")
            if page: page.update()

    async def _upload_files_async():
        upload_ring.visible = True
        status_text.value = "Abrindo seletor de arquivos..."
        status_text.color = _color("texto_sec", dark)
        page.update()

        file_paths = await _pick_study_files(page)
        if not file_paths:
            upload_ring.visible = False
            status_text.value = "Selecao cancelada."
            page.update()
            return

        if (not _is_premium_active(user)) and len(file_paths) > 1:
            upload_ring.visible = False
            status_text.value = "Plano Free: envie apenas 1 arquivo por vez na Biblioteca."
            status_text.color = CORES["warning"]
            page.update()
            _show_upgrade_dialog(page, navigate, "No Premium, o upload na Biblioteca e ilimitado por envio.")
            return

        count = 0
        try:
            for path in file_paths:
                library_service.adicionar_arquivo(user["id"], path)
                count += 1
            status_text.value = f"{count} arquivo(s) adicionado(s) com sucesso!"
            status_text.color = CORES["sucesso"]
            _refresh_list()
        except Exception as ex:
            log_exception(ex, "_upload_files_async")
            status_text.value = f"Erro no upload: {ex}"
            status_text.color = CORES["erro"]
        finally:
            upload_ring.visible = False
            page.update()

    def _upload_click(_):
        if page:
            page.run_task(_upload_files_async)

    _refresh_list()
    _refresh_packages()
    return ft.Container(
        expand=True,
        bgcolor=_color("fundo", dark),
        padding=20,
        content=ft.Column([
            ft.Text("Minha Biblioteca", size=28, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
            ft.Text("Gerencie seus materiais de estudo. Use-os para gerar quizzes personalizados.", size=14, color=_color("texto_sec", dark)),
            ft.ResponsiveRow(
                controls=[
                    ft.Container(
                        col={"sm": 6, "md": 3},
                        content=ft.Card(
                            elevation=1,
                            content=ft.Container(
                                padding=12,
                                content=ft.Column(
                                    [ft.Text("Arquivos", size=12, color=_color("texto_sec", dark)), files_count_text],
                                    spacing=4,
                                ),
                            ),
                        ),
                    ),
                    ft.Container(
                        col={"sm": 6, "md": 3},
                        content=ft.Card(
                            elevation=1,
                            content=ft.Container(
                                padding=12,
                                content=ft.Column(
                                    [ft.Text("Pacotes", size=12, color=_color("texto_sec", dark)), packs_count_text],
                                    spacing=4,
                                ),
                            ),
                        ),
                    ),
                ],
                spacing=8,
                run_spacing=8,
            ),
            ft.Card(
                elevation=1,
                content=ft.Container(
                    padding=12,
                    content=ft.Column(
                        [
                            ft.Row([
                                ft.Text("Acoes", size=16, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                ft.Container(expand=True),
                                ft.ElevatedButton(
                                    "Adicionar PDF",
                                    icon=ft.Icons.UPLOAD_FILE,
                                    on_click=_upload_click,
                                    style=ft.ButtonStyle(bgcolor=CORES["primaria"], color="white"),
                                ),
                            ], wrap=True, spacing=8),
                            ft.Row([status_text, upload_ring], wrap=True, spacing=8),
                        ],
                        spacing=8,
                    ),
                ),
            ),
            ft.Card(
                elevation=1,
                content=ft.Container(
                    padding=12,
                    content=ft.Column(
                        [
                            ft.Text("Pacotes de Estudo", size=16, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                            package_list,
                        ],
                        spacing=8,
                    ),
                ),
            ),
            ft.Card(
                elevation=1,
                content=ft.Container(
                    padding=12,
                    content=ft.Column(
                        [
                            ft.Text("Arquivos", size=16, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                            file_list,
                        ],
                        spacing=8,
                    ),
                ),
            ),
        ], expand=True, spacing=12, scroll=ft.ScrollMode.AUTO),
    )


def _build_splash(page: ft.Page, navigate, dark: bool):
    # Splash usa fundo escuro fixo para realÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â§ar a logo
    splash_bg = "#1c1c1c"
    logo, has_image = _logo_control(True)

    logo_box = ft.Container(
        content=logo,
        width=180,
        height=180,
        alignment=ft.Alignment(0, 0),
        animate_size=ft.Animation(350, ft.AnimationCurve.EASE_IN_OUT),
        opacity=0,
        animate_opacity=ft.Animation(300, ft.AnimationCurve.EASE_IN_OUT),
    )

    tagline = ft.Text("Vamos avancar hoje", size=16, color="#cbd5e1", opacity=0,
                      animate_opacity=ft.Animation(300, ft.AnimationCurve.EASE_IN_OUT))

    view = ft.View(
        route="/splash",
        controls=[
            ft.Container(
                expand=True,
                bgcolor=splash_bg,
        content=ft.Container(
            expand=True,
            opacity=1,
            animate_opacity=ft.Animation(250, ft.AnimationCurve.EASE_IN_OUT),
                    content=ft.Column(
                        [
                            logo_box,
                            ft.Text("Quiz Vance", size=32, weight=ft.FontWeight.BOLD, color=CORES["fundo"]) if not has_image else ft.Container(),
                            ft.Text("Estude com foco. Avance com pratica.", color="#cbd5e1"),
                            tagline,
                        ],
                        spacing=12,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        alignment=ft.Alignment(0, 0),
                    ),
                ),
            )
        ],
        bgcolor=splash_bg,
    )
    return view, logo_box, tagline




def _build_quiz_body(state, navigate, dark: bool):
    page = state.get("page")
    screen_w = _screen_width(page) if page else 1280
    compact = screen_w < 1000
    very_compact = screen_w < 760
    field_w_small = max(140, min(220, int(screen_w - 120)))
    user = state.get("usuario") or {}
    db = state.get("db")
    library_service = LibraryService(db) if db else None

    # Persist session to evitar reset ao mudar tema/rota
    session = state.get("quiz_session")
    if not session:
        session = {
            "questoes": [],
            "estado": {
                "respostas": {},
                "corrigido": False,
                "upload_texts": [],
                "upload_names": [],
                "favoritas": set(),
                "marcadas_erro": set(),
                "current_idx": 0,
                "feedback_imediato": True,
                "simulado_mode": False,
                "modo_continuo": False,
                "start_time": None,
                "confirmados": set(),
                "ultimo_filtro": {},
                "advanced_filters_draft": QuizFilterService.empty_filters(),
                "advanced_filters_applied": QuizFilterService.empty_filters(),
                "mock_exam_session_id": None,
                "mock_exam_started_at": None,
                "prova_deadline": None,
                "tempo_limite_s": None,
                "simulado_report": None,
                "simulado_items": [],
                "question_time_ms": {},
                "question_last_ts": None,
            },
        }
        state["quiz_session"] = session

    questoes = session["questoes"]
    estado = session["estado"]
    estado.setdefault("advanced_filters_draft", QuizFilterService.empty_filters())
    estado.setdefault("advanced_filters_applied", QuizFilterService.empty_filters())
    estado.setdefault("mock_exam_session_id", None)
    estado.setdefault("mock_exam_started_at", None)
    estado.setdefault("prova_deadline", None)
    estado.setdefault("tempo_limite_s", None)
    estado.setdefault("simulado_report", None)
    estado.setdefault("simulado_items", [])
    estado.setdefault("question_time_ms", {})
    estado.setdefault("question_last_ts", None)
    cards_column = ft.Column(
        spacing=12,
        expand=False,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )
    mapa_prova_wrap = ft.Row(wrap=True, spacing=6, run_spacing=6)
    mapa_prova_container = ft.Container(
        visible=False,
        padding=10,
        border_radius=10,
        bgcolor=_color("card", dark),
        content=ft.Column(
            [
                ft.Text("Mapa da prova", size=12, weight=ft.FontWeight.W_600, color=_color("texto", dark)),
                mapa_prova_wrap,
            ],
            spacing=8,
        ),
    )
    simulado_report_column = ft.Column(controls=[], spacing=DS.SP_8, visible=False)
    resultado = ft.Text("", weight=ft.FontWeight.BOLD)
    resultado_box = ft.Container(
        padding=10,
        border_radius=8,
        bgcolor=_color("card", dark),
        content=resultado,
        visible=False,
    )
    carregando = ft.ProgressRing(width=30, height=30, visible=False)
    status_text = ft.Text("", size=12, weight=ft.FontWeight.W_400, color=_color("texto_sec", dark))
    status_estudo = ft.Text("", size=12, weight=ft.FontWeight.W_400, color=_color("texto_sec", dark))
    status_box = _status_banner(status_text, dark)
    status_box.visible = False
    status_estudo_box = _status_banner(status_estudo, dark)
    status_estudo_box.visible = False
    recomendacao_text = ft.Text("", size=12, weight=ft.FontWeight.W_400, color=_color("texto_sec", dark), visible=False)
    recomendacao_button = ft.ElevatedButton("Proxima acao", icon=ft.Icons.NAVIGATE_NEXT, visible=False)
    contador_text = ft.Text("", size=12, color=_color("texto_sec", dark))
    progresso_text = ft.Text("0/0 respondidas", size=12, color=_color("texto_sec", dark))
    tempo_text = ft.Text("Tempo: 00:00", size=12, color=_color("texto_sec", dark))
    preview_count_text = ft.Text("10", size=13, weight=ft.FontWeight.BOLD, color=_color("texto", dark))
    etapa_text = ft.Text("Etapa 1 de 2: configure e gere", size=13, weight=ft.FontWeight.W_500, color=_color("texto_sec", dark))
    filtro_resumo_text = ft.Text("", size=12, color=_color("texto_sec", dark))
    upload_info = ft.Text("Nenhum material enviado.", size=12, weight=ft.FontWeight.W_400, color=_color("texto_sec", dark))
    ai_enabled = bool(_create_user_ai_service(user))

    def _sync_resultado_box_visibility():
        resultado_box.visible = bool(str(resultado.value or "").strip()) and bool(estado.get("corrigido"))

    dificuldade_padrao = "intermediario" if "intermediario" in DIFICULDADES else next(iter(DIFICULDADES))
    difficulty_dropdown = ft.Dropdown(
        label="Dificuldade",
        width=field_w_small if compact else 220,
        options=[ft.dropdown.Option(key=key, text=cfg["nome"]) for key, cfg in DIFICULDADES.items()],
        value=dificuldade_padrao,
    )
    quiz_count_dropdown = ft.Dropdown(
        label="Quantidade",
        width=field_w_small if compact else 240,
        options=[
            ft.dropdown.Option(key="10", text="10 questoes"),
            ft.dropdown.Option(key="20", text="20 questoes"),
            ft.dropdown.Option(key="30", text="30 questoes"),
            ft.dropdown.Option(key="cont", text="Continuo"),
        ],
        value="10",
    )
    def _on_count_change(e):
        val = e.control.value or "10"
        preview_count_text.value = "\u221e" if val == "cont" else str(val)
        if page:
            page.update()
    quiz_count_dropdown.on_change = _on_count_change
    session_mode_dropdown = ft.Dropdown(
        label="Sessao",
        width=field_w_small if compact else 220,
        options=[
            ft.dropdown.Option(key="nova", text="Nova sessao"),
            ft.dropdown.Option(key="erradas", text="Erradas recentes"),
            ft.dropdown.Option(key="favoritas", text="Favoritas"),
            ft.dropdown.Option(key="nao_resolvidas", text="Nao resolvidas"),
        ],
        value="nova",
    )
    simulado_mode_switch = ft.Switch(label="Modo prova", value=bool(estado.get("simulado_mode", False)))
    feedback_policy_text = ft.Text("", size=11, color=_color("texto_sec", dark))

    def _sync_feedback_policy_ui():
        is_prova = bool(simulado_mode_switch.value)
        estado["simulado_mode"] = is_prova
        estado["feedback_imediato"] = not is_prova
        feedback_policy_text.value = (
            "Feedback: correcao apenas ao encerrar a prova."
            if is_prova
            else "Feedback: imediato (sempre ativo fora do modo prova)."
        )

    def _on_simulado_mode_change(_=None):
        _sync_feedback_policy_ui()
        if page:
            page.update()

    simulado_mode_switch.on_change = _on_simulado_mode_change
    _sync_feedback_policy_ui()
    save_filter_name = ft.TextField(label="Salvar filtro como", width=field_w_small if compact else 240, hint_text="Ex.: Revisao Direito")
    saved_filters_dropdown = ft.Dropdown(label="Filtros salvos", width=field_w_small if compact else 280, options=[])

    preset = state.pop("quiz_preset", None)
    package_questions = state.pop("quiz_package_questions", None)

    topic_field = ft.TextField(
        label="Topico (opcional)",
        hint_text="Ex.: Direito Administrativo ou Sistemas Distribuidos",
        expand=True,
    )
    referencia_field = ft.TextField(
        label="Conteudo de referencia (opcional)",
        hint_text="Cole texto, resumo ou instrucoes especificas para a IA.",
        expand=True,
        min_lines=3,
        max_lines=6,
        multiline=True,
    )
    advanced_section_labels = {
        "disciplinas": "Disciplinas",
        "assuntos": "Assuntos",
        "bancas": "Bancas",
        "cargos": "Cargos",
        "anos": "Anos",
        "status": "Status",
    }
    advanced_filters_button = ft.OutlinedButton("Filtros avancados (0)", icon=ft.Icons.TUNE)
    advanced_filters_hint = ft.Text("Sem filtros avancados", size=11, color=_color("texto_sec", dark))

    def _get_applied_advanced_filters() -> dict:
        return QuizFilterService.normalize_filters(estado.get("advanced_filters_applied") or {})

    def _set_applied_advanced_filters(value: dict):
        estado["advanced_filters_applied"] = QuizFilterService.normalize_filters(value)
        total = QuizFilterService.selection_count(estado["advanced_filters_applied"])
        advanced_filters_button.text = f"Filtros avancados ({total})"
        advanced_filters_hint.value = QuizFilterService.summary(estado["advanced_filters_applied"], max_items=8)
        filtro_resumo_text.value = (
            f"Filtro ativo: {advanced_filters_hint.value}"
            if total > 0
            else "Filtro ativo: sem filtros avancados"
        )

    def _open_advanced_filters_dialog(_=None):
        if not page:
            return
        estado["advanced_filters_draft"] = QuizFilterService.normalize_filters(_get_applied_advanced_filters())
        search_map = {sec: "" for sec in QuizFilterService.SECTIONS}
        dialog_ref = {"dlg": None}

        def _toggle_chip(section: str, option_id: str):
            draft = QuizFilterService.normalize_filters(estado.get("advanced_filters_draft") or {})
            estado["advanced_filters_draft"] = QuizFilterService.toggle_value(draft, section, option_id)
            _render_dialog_content()
            page.update()

        def _set_search(section: str, value: str):
            search_map[section] = str(value or "")
            _render_dialog_content()
            page.update()

        def _render_section(section: str) -> ft.Control:
            draft = QuizFilterService.normalize_filters(estado.get("advanced_filters_draft") or {})
            selected = set(draft.get(section) or [])
            options = QuizFilterService.filtered_options(section, search_map.get(section) or "")
            chips = [
                ds_chip(
                    str(item.get("label") or item.get("id") or ""),
                    selected=str(item.get("id") or "") in selected,
                    on_click=lambda _, s=section, oid=str(item.get("id") or ""): _toggle_chip(s, oid),
                    dark=dark,
                    small=True,
                )
                for item in options
            ]
            if not chips:
                chips = [ft.Text("Nenhuma opcao para este filtro.", size=11, color=_color("texto_sec", dark))]
            return ds_card(
                dark=dark,
                padding=DS.SP_12,
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(advanced_section_labels.get(section, section.title()), size=13, weight=ft.FontWeight.W_600, color=_color("texto", dark)),
                                ft.Container(expand=True),
                                ds_badge(str(len(selected)), color=DS.P_500 if len(selected) else DS.G_500),
                            ]
                        ),
                        ft.TextField(
                            label="Buscar",
                            hint_text=f"Filtrar {advanced_section_labels.get(section, section)}",
                            value=search_map.get(section) or "",
                            on_change=lambda e, s=section: _set_search(s, getattr(e.control, "value", "")),
                            dense=True,
                        ),
                        ft.Row(chips, wrap=True, spacing=6),
                    ],
                    spacing=8,
                ),
            )

        def _render_dialog_content():
            draft = QuizFilterService.normalize_filters(estado.get("advanced_filters_draft") or {})
            total = QuizFilterService.selection_count(draft)
            dialog_ref["dlg"].title = ft.Text(f"Filtros avancados ({total})")
            dialog_ref["dlg"].content = ft.Container(
                width=min(980, max(420, int(_screen_width(page) * 0.92))),
                height=min(760, max(460, int(_screen_height(page) * 0.86))),
                content=ft.Column(
                    [
                        ft.Text(
                            "Aplique filtros por secoes com busca e contadores.",
                            size=12,
                            color=_color("texto_sec", dark),
                        ),
                        _render_section("disciplinas"),
                        _render_section("assuntos"),
                        _render_section("bancas"),
                        _render_section("cargos"),
                        _render_section("anos"),
                        _render_section("status"),
                    ],
                    spacing=10,
                    scroll=ft.ScrollMode.ALWAYS,
                ),
            )

        def _apply_filters(_):
            _set_applied_advanced_filters(estado.get("advanced_filters_draft") or {})
            _close_dialog_compat(page, dialog_ref["dlg"])
            _set_feedback_text(status_text, "Filtros avancados aplicados.", "success")
            _refresh_status_boxes()
            page.update()

        def _clear_filters(_):
            estado["advanced_filters_draft"] = QuizFilterService.empty_filters()
            _render_dialog_content()
            page.update()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Filtros avancados"),
            content=ft.Container(),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: _close_dialog_compat(page, dlg)),
                ft.TextButton("Limpar", on_click=_clear_filters),
                ft.ElevatedButton("Aplicar", on_click=_apply_filters),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        dialog_ref["dlg"] = dlg
        _render_dialog_content()
        _show_dialog_compat(page, dlg)

    advanced_filters_button.on_click = _open_advanced_filters_dialog

    if isinstance(preset, dict):
        topic_field.value = str(preset.get("topic") or "")
        difficulty_dropdown.value = str(preset.get("difficulty") or dificuldade_padrao)
        quiz_count_dropdown.value = str(preset.get("count") or "10")
        preview_count_text.value = "\u221e" if quiz_count_dropdown.value == "cont" else str(quiz_count_dropdown.value or "10")
        session_mode_dropdown.value = str(preset.get("session_mode") or "nova")
        simulado_mode_switch.value = bool(preset.get("simulado_mode", False))
        _sync_feedback_policy_ui()
        if preset.get("simulado_tempo") is not None:
            try:
                estado["tempo_limite_s"] = max(300, int(preset.get("simulado_tempo")) * 60)
            except Exception:
                estado["tempo_limite_s"] = 60 * 60
        _set_applied_advanced_filters(preset.get("advanced_filters") or {})
        status_text.value = str(preset.get("reason") or "Preset aplicado.")
    else:
        _set_applied_advanced_filters(estado.get("advanced_filters_applied") or {})

    # dropdown da biblioteca
    library_opts = []
    if library_service and user.get("id"):
        library_files = library_service.listar_arquivos(user["id"])
        library_opts = [ft.dropdown.Option(str(f["id"]), text=f["nome_arquivo"]) for f in library_files]
    
    async def _on_library_select(e):
        fid = e.control.value
        if not fid: return
        
        texto = library_service.get_conteudo_arquivo(int(fid))
        if texto:
            nome = next((f["nome_arquivo"] for f in library_files if str(f["id"]) == fid), "Arquivo Biblioteca")
            estado["upload_texts"].append(texto)
            estado["upload_names"].append(f"[LIB] {nome}")
            _set_upload_info()
            status_text.value = f"Adicionado da biblioteca: {nome}"
            # Resetar dropdown para permitir selecionar outro
            e.control.value = None
            e.control.update()
            if page: page.update()

    library_dropdown = ft.Dropdown(
        label="Adicionar da Biblioteca",
        width=field_w_small if compact else 300,
        options=library_opts,
        disabled=not library_opts
    )
    library_dropdown.on_change = _on_library_select

    def _normalize_question_for_ui(q: dict) -> Optional[dict]:
        if not isinstance(q, dict):
            return None
        q = _sanitize_payload_texts(q)
        enunciado = _fix_mojibake_text(str(q.get("enunciado") or q.get("pergunta") or "")).strip()
        alternativas = q.get("alternativas") or q.get("opcoes") or []
        if not enunciado or not isinstance(alternativas, list) or len(alternativas) < 2:
            return None
        alternativas = [
            _fix_mojibake_text(str(a)).strip()
            for a in alternativas
            if _fix_mojibake_text(str(a)).strip()
        ]
        if len(alternativas) < 2:
            return None
        correta_idx = q.get("correta_index", q.get("correta", 0))
        try:
            correta_idx = int(correta_idx)
        except Exception:
            correta_idx = 0
        correta_idx = max(0, min(correta_idx, len(alternativas) - 1))
        out = {
            "enunciado": enunciado,
            "alternativas": alternativas[:4],
            "correta_index": correta_idx,
        }
        if q.get("explicacao"):
            out["explicacao"] = _fix_mojibake_text(str(q.get("explicacao")))
        if q.get("tema"):
            out["tema"] = _fix_mojibake_text(str(q.get("tema")))
        if q.get("assunto"):
            out["assunto"] = _fix_mojibake_text(str(q.get("assunto")))
        if q.get("_meta"):
            out["_meta"] = _sanitize_payload_texts(q.get("_meta"))
        return out

    def _current_filter_payload() -> dict:
        count_raw = str(quiz_count_dropdown.value or "5")
        count_val = int(count_raw) if count_raw.isdigit() else count_raw
        return {
            "topic": (topic_field.value or "").strip(),
            "difficulty": difficulty_dropdown.value or dificuldade_padrao,
            "count": count_val,
            "session_mode": session_mode_dropdown.value or "nova",
            "feedback_imediato": not bool(simulado_mode_switch.value),
            "simulado_mode": bool(simulado_mode_switch.value),
            "advanced_filters": _get_applied_advanced_filters(),
        }

    def _load_saved_filters():
        if not db or not user.get("id"):
            saved_filters_dropdown.options = []
            return
        try:
            filtros = db.listar_filtros_quiz(user["id"])
            saved_filters_dropdown.options = [
                ft.dropdown.Option(key=str(f["id"]), text=f["nome"])
                for f in filtros
            ]
            saved_filters_dropdown.data = {str(f["id"]): f for f in filtros}
        except Exception as ex:
            log_exception(ex, "main._build_quiz_body._load_saved_filters")
            saved_filters_dropdown.options = []
            saved_filters_dropdown.data = {}

    def _apply_saved_filter(e):
        key = e.control.value
        if not key:
            return
        data_map = getattr(saved_filters_dropdown, "data", {}) or {}
        item = data_map.get(key)
        if not item:
            return
        filtro = item.get("filtro", {})
        topic_field.value = filtro.get("topic", "")
        difficulty_dropdown.value = filtro.get("difficulty", dificuldade_padrao)
        quiz_count_dropdown.value = str(filtro.get("count", 5))
        session_mode_dropdown.value = filtro.get("session_mode", "nova")
        simulado_mode_switch.value = bool(filtro.get("simulado_mode", False))
        _sync_feedback_policy_ui()
        _set_applied_advanced_filters(filtro.get("advanced_filters") or {})
        status_text.value = f"Filtro aplicado: {item.get('nome', '')}"
        if page:
            page.update()

    def _save_current_filter(_):
        if not db or not user.get("id"):
            _set_feedback_text(status_text, "Entre na conta para salvar filtros (backup e sync).", "warning")
            _refresh_status_boxes()
            if page:
                page.update()
            navigate("/login")
            return
        nome = (save_filter_name.value or "").strip()
        if not nome:
            status_text.value = "Informe um nome para salvar o filtro."
            if page:
                page.update()
            return
        try:
            db.salvar_filtro_quiz(user["id"], nome, _current_filter_payload())
            _emit_opt_in_event(user, "save_filter_clicked", "quiz_filter")
            save_filter_name.value = ""
            _load_saved_filters()
            status_text.value = f"Filtro salvo: {nome}"
            if page:
                page.update()
        except Exception as ex:
            log_exception(ex, "main._build_quiz_body._save_current_filter")
            status_text.value = "Falha ao salvar filtro."
            if page:
                page.update()

    def _delete_selected_filter(_):
        if not db or not user.get("id"):
            return
        key = saved_filters_dropdown.value
        if not key:
            status_text.value = "Selecione um filtro salvo para excluir."
            if page:
                page.update()
            return
        try:
            db.excluir_filtro_quiz(int(key), user["id"])
            saved_filters_dropdown.value = None
            _load_saved_filters()
            status_text.value = "Filtro excluido."
            if page:
                page.update()
        except Exception as ex:
            log_exception(ex, "main._build_quiz_body._delete_selected_filter")

    saved_filters_dropdown.on_change = _apply_saved_filter

    def _update_session_meta():
        total = len(questoes)
        respondidas = len([k for k, v in estado["respostas"].items() if v is not None])
        progresso_text.value = f"{respondidas}/{total} respondidas"
        if estado.get("simulado_mode") and estado.get("prova_deadline"):
            restante = int(max(0, float(estado.get("prova_deadline") or 0) - time.monotonic()))
            tempo_text.value = f"Tempo restante: {restante // 60:02d}:{restante % 60:02d}"
        elif estado.get("start_time"):
            elapsed = int(max(0, time.monotonic() - estado["start_time"]))
            tempo_text.value = f"Tempo: {elapsed // 60:02d}:{elapsed % 60:02d}"
        else:
            tempo_text.value = "Tempo: 00:00"

    def _refresh_status_boxes():
        status_box.visible = bool(status_text.value.strip())
        status_estudo_box.visible = bool(status_estudo.value.strip())

    def _refresh_filter_summary():
        total = QuizFilterService.selection_count(_get_applied_advanced_filters())
        text = QuizFilterService.summary(_get_applied_advanced_filters(), max_items=8)
        if total > 0:
            filtro_resumo_text.value = f"Filtro ativo: {text}"
        else:
            filtro_resumo_text.value = "Filtro ativo: sem filtros avancados"

    def _set_upload_info():
        names = estado["upload_names"]
        if not names:
            upload_info.value = "Nenhum material enviado."
            return
        preview = ", ".join(names[:3])
        if len(names) > 3:
            preview += f" +{len(names) - 3}"
        upload_info.value = f"{len(names)} arquivo(s): {preview}"

    async def _pick_files_async():
        if not page:
            return
        _set_feedback_text(status_text, "Abrindo seletor de arquivos...", "info")
        page.update()
        file_paths = await _pick_study_files(page)
        if not file_paths:
            _set_feedback_text(status_text, "Selecao cancelada.", "info")
            page.update()
            return
        upload_texts, upload_names = _extract_uploaded_material(file_paths)
        estado["upload_texts"] = upload_texts
        estado["upload_names"] = upload_names
        if not upload_texts:
            _set_feedback_text(status_text, "Arquivos sem texto legivel. Use PDF/TXT/MD.", "warning")
        else:
            _set_feedback_text(status_text, f"Material carregado: {len(upload_texts)} arquivo(s).", "success")
        _set_upload_info()
        page.update()

    def _upload_material(_):
        if not page:
            return
        page.run_task(_pick_files_async)

    def _limpar_material(_):
        estado["upload_texts"] = []
        estado["upload_names"] = []
        _set_upload_info()
        _set_feedback_text(status_text, "Material removido.", "info")
        if page:
            page.update()

    async def _on_explain_click(q_idx):
        if not page: return
        
        # Mostrar loading
        dlg = ft.AlertDialog(
            title=ft.Text("Consultando IA..."),
            content=ft.Column([ft.ProgressRing(), ft.Text("Gerando explicacao simplificada...")], tight=True, alignment=ft.MainAxisAlignment.CENTER),
            modal=True
        )
        _show_dialog_compat(page, dlg)
        
        # Obter dados
        questao = questoes[q_idx]
        pergunta_txt = _fix_mojibake_text(str(questao.get("enunciado") or ""))
        correta_idx = questao.get("correta_index", 0)
        alternativas = list(questao.get("alternativas") or [])
        correta_idx = max(0, min(int(correta_idx or 0), max(0, len(alternativas) - 1)))
        resposta_txt = _fix_mojibake_text(str(alternativas[correta_idx] if alternativas else ""))
        
        # Chamar AI
        service = _create_user_ai_service(user)
        explicacao = "Erro ao conectar com IA."
        if service:
            explicacao = await asyncio.to_thread(service.explain_simple, pergunta_txt, resposta_txt)
        explicacao = _fix_mojibake_text(str(explicacao or ""))
            
        # Fechar loading e mostrar resultado
        _close_dialog_compat(page, dlg)
        
        await asyncio.sleep(0.1)
        
        res_dlg = ft.AlertDialog(
            title=ft.Text("Explicacao Simplificada"),
            content=ft.Text(explicacao, size=15),
            actions=[ft.TextButton("Entendi", on_click=lambda e: _close_dialog_compat(page, res_dlg))],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        _show_dialog_compat(page, res_dlg)

    def _persist_question_flags(qidx: int, tentativa_correta: Optional[bool] = None):
        if not db or not user.get("id"):
            return
        if qidx < 0 or qidx >= len(questoes):
            return
        q = questoes[qidx]
        tema = (topic_field.value or "").strip() or q.get("tema", "Geral")
        dificuldade = difficulty_dropdown.value or dificuldade_padrao
        try:
            db.registrar_questao_usuario(
                user["id"],
                q,
                tema=tema,
                dificuldade=dificuldade,
                tentativa_correta=tentativa_correta,
                favorita=(qidx in estado["favoritas"]),
                marcado_erro=(qidx in estado["marcadas_erro"]),
            )
        except Exception as ex:
            log_exception(ex, "main._build_quiz_body._persist_question_flags")

    def _next_question(_=None):
        if not questoes:
            return
        _track_question_time()
        estado["current_idx"] = min(len(questoes) - 1, estado["current_idx"] + 1)
        _persist_mock_progress()
        _rebuild_cards()
        if page:
            page.update()

    def _prev_question(_=None):
        if not questoes:
            return
        _track_question_time()
        estado["current_idx"] = max(0, estado["current_idx"] - 1)
        _persist_mock_progress()
        _rebuild_cards()
        if page:
            page.update()

    def _skip_question(_=None):
        if questoes:
            idx = int(max(0, min(len(questoes) - 1, estado.get("current_idx", 0))))
            estado["respostas"][idx] = None
            estado["confirmados"].add(idx)
            _track_question_time()
            _persist_mock_progress()
        _next_question()

    def _toggle_favorita(_=None):
        qidx = estado.get("current_idx", 0)
        if qidx in estado["favoritas"]:
            estado["favoritas"].remove(qidx)
        else:
            estado["favoritas"].add(qidx)
        _persist_question_flags(qidx, None)
        _rebuild_cards()
        if page:
            page.update()

    def _toggle_marcada_erro(_=None):
        qidx = estado.get("current_idx", 0)
        if qidx in estado["marcadas_erro"]:
            estado["marcadas_erro"].remove(qidx)
        else:
            estado["marcadas_erro"].add(qidx)
        _persist_question_flags(qidx, None)
        _rebuild_cards()
        if page:
            page.update()

    def _report_question_issue(_=None):
        if not questoes:
            return
        qidx = int(max(0, min(len(questoes) - 1, estado.get("current_idx", 0))))
        estado["marcadas_erro"].add(qidx)
        _persist_question_flags(qidx, None)
        _set_feedback_text(status_estudo, "Questao reportada e marcada para revisao.", "info")
        _refresh_status_boxes()
        _rebuild_cards()
        if page:
            page.update()

    timer_ref = {"token": 0, "task": None}

    def _cancel_timer_task():
        task = timer_ref.get("task")
        if task and hasattr(task, "cancel"):
            try:
                task.cancel()
            except Exception:
                pass
        timer_ref["task"] = None

    def _track_question_time():
        if not questoes:
            estado["question_last_ts"] = time.monotonic()
            return
        now = time.monotonic()
        last = estado.get("question_last_ts")
        if last is None:
            estado["question_last_ts"] = now
            return
        idx = int(max(0, min(len(questoes) - 1, estado.get("current_idx", 0))))
        delta_ms = int(max(0.0, now - float(last)) * 1000)
        if delta_ms > 0:
            times = dict(estado.get("question_time_ms") or {})
            times[idx] = int(times.get(idx, 0) or 0) + delta_ms
            estado["question_time_ms"] = times
        estado["question_last_ts"] = now

    def _reset_mock_exam_runtime(clear_mode: bool = False):
        _cancel_timer_task()
        estado["simulado_report"] = None
        estado["simulado_items"] = []
        estado["mock_exam_session_id"] = None
        estado["mock_exam_started_at"] = None
        estado["prova_deadline"] = None
        estado["question_time_ms"] = {}
        estado["question_last_ts"] = None
        simulado_report_column.visible = False
        simulado_report_column.controls = []
        if clear_mode:
            estado["simulado_mode"] = False
            estado["tempo_limite_s"] = None

    def _question_simulado_meta(question: dict) -> dict:
        meta = question.get("_meta") or {}
        disciplina = str(meta.get("disciplina") or question.get("tema") or topic_field.value or "Geral").strip() or "Geral"
        assunto = str(meta.get("assunto") or question.get("assunto") or "Geral").strip() or "Geral"
        return {"disciplina": disciplina, "assunto": assunto, "tema": disciplina}

    def _persist_mock_progress():
        if not (db and user.get("id") and estado.get("simulado_mode") and estado.get("mock_exam_session_id")):
            return
        try:
            db.salvar_mock_exam_progresso(
                int(estado.get("mock_exam_session_id")),
                int(estado.get("current_idx") or 0),
                dict(estado.get("respostas") or {}),
            )
        except Exception as ex:
            log_exception(ex, "main._build_quiz_body._persist_mock_progress")

    def _render_mapa_prova():
        if not questoes or not bool(estado.get("simulado_mode")):
            mapa_prova_container.visible = False
            mapa_prova_wrap.controls = []
            return
        mapa_prova_wrap.controls = []
        for idx in range(len(questoes)):
            answered = (estado.get("respostas") or {}).get(idx) is not None
            confirmed = idx in set(estado.get("confirmados") or set())
            is_current = idx == int(estado.get("current_idx") or 0)
            if is_current:
                color = DS.P_500
            elif confirmed and answered:
                color = DS.SUCESSO
            elif answered:
                color = DS.WARNING
            else:
                color = DS.G_500
            mapa_prova_wrap.controls.append(
                ft.Container(
                    width=32,
                    height=32,
                    alignment=ft.Alignment(0, 0),
                    border_radius=8,
                    bgcolor=ft.Colors.with_opacity(0.16, color),
                    border=ft.border.all(1, color),
                    content=ft.Text(str(idx + 1), size=11, weight=ft.FontWeight.W_600, color=color),
                    on_click=lambda _, i=idx: _go_to_question(i),
                )
            )
        mapa_prova_container.visible = True

    def _go_to_question(idx: int):
        if not questoes:
            return
        _track_question_time()
        estado["current_idx"] = max(0, min(len(questoes) - 1, int(idx)))
        _persist_mock_progress()
        _rebuild_cards()
        if page:
            page.update()

    def _ensure_mock_exam_session(total_questoes: int):
        if not (db and user.get("id") and bool(estado.get("simulado_mode"))):
            return
        if estado.get("mock_exam_session_id"):
            return
        try:
            tempo_total_s = int(max(0, estado.get("tempo_limite_s") or 0))
            filtro_snapshot = _current_filter_payload()
            sid = db.criar_mock_exam_session(
                int(user["id"]),
                filtro_snapshot=filtro_snapshot,
                total_questoes=int(max(1, total_questoes)),
                tempo_total_s=tempo_total_s,
                modo="timed" if tempo_total_s > 0 else "treino",
            )
            estado["mock_exam_session_id"] = int(sid)
            estado["mock_exam_started_at"] = time.monotonic()
            _persist_mock_progress()
        except Exception as ex:
            log_exception(ex, "main._build_quiz_body._ensure_mock_exam_session")

    async def _cronometro_task(token: int):
        while True:
            if token != timer_ref.get("token"):
                return
            if not bool(estado.get("simulado_mode")):
                return
            deadline = float(estado.get("prova_deadline") or 0)
            if deadline <= 0:
                return
            restante = int(max(0, deadline - time.monotonic()))
            _update_session_meta()
            if page:
                page.update()
            if restante <= 0:
                try:
                    corrigir(None, forcar_timeout=True)
                except Exception as ex:
                    log_exception(ex, "main._build_quiz_body._cronometro_task.timeout")
                return
            await asyncio.sleep(1.0)

    def _rebuild_cards():
        cards_column.controls.clear()
        _sync_resultado_box_visibility()
        sw = _screen_width(page) if page else 1280
        sh = _screen_height(page) if page else 820
        mobile = sw < 760
        q_font = 16 if sw < 520 else (18 if sw < 760 else (21 if sw < 1000 else 26))
        if not questoes:
            cards_column.controls.append(
                ft.Container(
                    padding=14,
                    border_radius=10,
                    bgcolor=_color("card", dark),
                    content=ft.Text("Nenhuma questao carregada.", color=_color("texto_sec", dark)),
                )
            )
            contador_text.value = "0 questoes prontas"
            progresso_text.value = "0/0 respondidas"
            tempo_text.value = "Tempo: 00:00"
            mapa_prova_container.visible = False
            mapa_prova_wrap.controls = []
            _refresh_status_boxes()
            return

        idx = int(max(0, min(len(questoes) - 1, estado.get("current_idx", 0))))
        estado["current_idx"] = idx
        pergunta = _normalize_question_for_ui(questoes[idx]) or _sanitize_payload_texts(dict(questoes[idx]))
        if isinstance(pergunta, dict):
            questoes[idx] = dict(pergunta)
        options = []
        correta_idx = int(pergunta.get("correta_index", pergunta.get("correta", 0)) or 0)
        selected = estado["respostas"].get(idx)
        is_corrigido = estado["corrigido"]
        if not estado.get("simulado_mode") and idx in estado["confirmados"]:
            is_corrigido = True

        alternativas = list(pergunta.get("alternativas") or [])
        for i, alt in enumerate(alternativas):
            fill_color = CORES["primaria"]
            opacity = 1.0
            if is_corrigido and selected is not None:
                if i == correta_idx:
                    fill_color = CORES["sucesso"]
                elif i == selected and i != correta_idx:
                    fill_color = CORES["erro"]
                else:
                    opacity = 0.55
            option_text = " ".join(str(alt or "").replace("\r", "\n").split())
            wrap_width = 30 if sw < 520 else (42 if sw < 760 else 58)
            option_text = textwrap.fill(
                option_text,
                width=wrap_width,
                break_long_words=False,
                break_on_hyphens=False,
            )
            options.append(ft.Radio(value=str(i), label=option_text, fill_color=fill_color, opacity=opacity))

        def _on_change(e):
            if estado["corrigido"] or idx in estado["confirmados"]:
                return
            valor = getattr(e.control, "value", None)
            if valor in (None, ""):
                valor = getattr(e, "data", None)
            try:
                estado["respostas"][idx] = int(valor) if valor not in (None, "", "null") else None
            except Exception:
                estado["respostas"][idx] = None
            if idx in estado["confirmados"]:
                estado["confirmados"].discard(idx)
            _persist_mock_progress()
            _update_session_meta()
            _rebuild_cards()
            if page:
                page.update()

        header_badges = []
        if idx in estado["favoritas"]:
            header_badges.append(ft.Icon(ft.Icons.STAR, color=CORES["warning"], size=18))
        if idx in estado["marcadas_erro"]:
            header_badges.append(ft.Icon(ft.Icons.FLAG, color=CORES["erro"], size=18))

        question_content_controls = [
            ft.Row(
                [
                    ft.Text(f"Questao {idx + 1}/{len(questoes)}", size=13, color=_color("texto_sec", dark)),
                    ft.Container(expand=True),
                    *header_badges,
                ]
            ),
            ft.Container(
                alignment=ft.Alignment(0, 0),
                padding=ft.padding.only(top=2, bottom=4),
                content=ft.Text(
                    _fix_mojibake_text(str(pergunta.get("enunciado") or "")),
                    weight=ft.FontWeight.BOLD,
                    color=_color("texto", dark),
                    size=q_font,
                    text_align=ft.TextAlign.LEFT if sw < 760 else ft.TextAlign.CENTER,
                    selectable=True,
                ),
            ),
            ft.RadioGroup(
                key=f"quiz-rg-{idx}",
                value=str(selected) if selected is not None else None,
                on_change=_on_change,
                content=ft.Column(options, spacing=6, tight=True),
                disabled=estado["corrigido"] or idx in estado["confirmados"],
            ),
        ]

        if (estado["corrigido"] or (not estado.get("simulado_mode"))) and selected is not None:
            feedback_color = CORES["sucesso"] if selected == correta_idx else CORES["erro"]
            feedback_msg = "Correto!" if selected == correta_idx else "Incorreto."
            question_content_controls.append(
                ft.Row(
                    [
                        ft.Text(feedback_msg, color=feedback_color, weight=ft.FontWeight.BOLD),
                        ft.Container(expand=True),
                        ft.TextButton(
                            "Ver explicacao",
                            icon=ft.Icons.PSYCHOLOGY,
                            on_click=lambda _, i=idx: page.run_task(_on_explain_click, i),
                            visible=ai_enabled,
                        ),
                    ]
                )
            )
            if selected != correta_idx:

                def _flashcards_do_erro(_=None):
                    card_seed = []
                    en = str(pergunta.get("enunciado") or "")
                    correta_txt = str((pergunta.get("alternativas") or [""])[correta_idx] if (pergunta.get("alternativas") or []) else "")
                    tema_seed = str(topic_field.value or pergunta.get("tema") or "Geral")
                    if en and correta_txt:
                        for n in range(1, 4):
                            card_seed.append(
                                {
                                    "frente": f"[Erro {n}] {en}",
                                    "verso": f"Resposta correta: {correta_txt}",
                                    "tema": tema_seed,
                                }
                            )
                    if card_seed:
                        state["flashcards_seed_cards"] = card_seed
                        navigate("/flashcards")

                def _praticar_assunto(_=None):
                    tema = str(pergunta.get("tema") or topic_field.value or "Geral").strip() or "Geral"
                    topic_field.value = tema
                    quiz_count_dropdown.value = "10"
                    simulado_mode_switch.value = False
                    _sync_feedback_policy_ui()
                    session_mode_dropdown.value = "nova"
                    _set_feedback_text(status_text, f"Praticando mais de: {tema}", "info")
                    if page:
                        page.update()
                    _on_gerar_clique(None)

                question_content_controls.append(
                    ft.ResponsiveRow(
                        [
                            ft.Container(
                                col={"xs": 12, "md": 7},
                                content=ft.OutlinedButton(
                                    "Gerar 3 flashcards do erro",
                                    icon=ft.Icons.STYLE_OUTLINED,
                                    on_click=_flashcards_do_erro,
                                    expand=True,
                                ),
                            ),
                            ft.Container(
                                col={"xs": 12, "md": 5},
                                content=ft.TextButton(
                                    "Praticar o tema",
                                    icon=ft.Icons.SCHOOL_OUTLINED,
                                    on_click=_praticar_assunto,
                                ),
                            ),
                        ],
                        run_spacing=6,
                        spacing=8,
                    )
                )

        def _confirm_and_next(_=None):
            current_idx = int(max(0, min(len(questoes) - 1, estado.get("current_idx", 0)))) if questoes else 0
            current_selected = (estado.get("respostas") or {}).get(current_idx)
            if current_selected is None:
                return
            if current_idx not in estado["confirmados"]:
                _confirmar()
            _next_question()

        compact_label = sw < 520
        prev_label = "Ant." if compact_label else "Anterior"
        next_label = "Prox." if compact_label else "Proxima"
        confirm_label = "Confirmar" if compact_label else "Confirmar resposta"
        fav_label = "Favorito" if compact_label else "Favoritar"
        err_label = "Erro" if compact_label else "Marcar erro"
        rep_label = "Reportar"

        note_default = ""
        if db and user.get("id"):
            try:
                note_default = db.obter_nota_questao(user["id"], pergunta)
            except Exception as ex:
                log_exception(ex, "main._build_quiz_body.obter_nota_questao")
        note_default = _fix_mojibake_text(str(note_default or ""))
        # Evita box gigante quando nota salva vem com quebras/markup inesperados.
        note_default = " ".join(note_default.replace("\r", "\n").split())
        if len(note_default) > 260:
            note_default = note_default[:260]
        note_field = ft.TextField(
            label="Anotacao (opcional)",
            value=note_default,
            multiline=False,
            min_lines=1,
            max_lines=1,
            height=46,
            dense=True,
            expand=True,
        )

        def _save_note(_):
            if not db or not user.get("id"):
                return
            try:
                db.salvar_nota_questao(user["id"], pergunta, note_field.value or "")
                status_estudo.value = "Anotacao salva."
                if page:
                    page.update()
            except Exception as ex:
                log_exception(ex, "main._build_quiz_body.salvar_nota_questao")
                status_estudo.value = "Falha ao salvar anotacao."
                if page:
                    page.update()

        action_section = ft.Column(
            [
                ft.ResponsiveRow(
                    [
                        ft.Container(
                            col={"xs": 6, "md": 3},
                            content=ft.OutlinedButton(prev_label, icon=ft.Icons.CHEVRON_LEFT, on_click=_prev_question, expand=True),
                        ),
                        ft.Container(
                            col={"xs": 6, "md": 3},
                            content=ft.OutlinedButton("Pular", icon=ft.Icons.SKIP_NEXT, on_click=_skip_question, expand=True),
                        ),
                        ft.Container(
                            col={"xs": 6, "md": 3},
                            content=ft.OutlinedButton(
                                next_label,
                                icon=ft.Icons.CHEVRON_RIGHT,
                                on_click=_confirm_and_next,
                                disabled=selected is None,
                                expand=True,
                            ),
                        ),
                        ft.Container(
                            col={"xs": 6, "md": 3},
                            content=ft.ElevatedButton(
                                confirm_label,
                                icon=ft.Icons.CHECK_CIRCLE,
                                on_click=_confirmar,
                                disabled=selected is None or idx in estado["confirmados"],
                                expand=True,
                            ),
                        ),
                    ],
                    run_spacing=6,
                    spacing=6,
                ),
                ft.ResponsiveRow(
                    [
                        ft.Container(
                            col={"xs": 4, "md": 4},
                            content=ft.TextButton(
                                fav_label,
                                icon=ft.Icons.STAR if idx in estado["favoritas"] else ft.Icons.STAR_BORDER,
                                on_click=_toggle_favorita,
                            ),
                        ),
                        ft.Container(
                            col={"xs": 4, "md": 4},
                            content=ft.TextButton(
                                err_label,
                                icon=ft.Icons.FLAG if idx in estado["marcadas_erro"] else ft.Icons.FLAG_OUTLINED,
                                on_click=_toggle_marcada_erro,
                            ),
                        ),
                        ft.Container(
                            col={"xs": 4, "md": 4},
                            content=ft.TextButton(
                                rep_label,
                                icon=ft.Icons.REPORT_GMAILERRORRED_OUTLINED,
                                on_click=_report_question_issue,
                            ),
                        ),
                    ],
                    run_spacing=4,
                    spacing=6,
                ),
                ft.ResponsiveRow(
                    [
                        ft.Container(col={"xs": 12, "md": 8}, content=note_field),
                        ft.Container(
                            col={"xs": 12, "md": 4},
                            content=ft.ElevatedButton(
                                "Salvar anotacao",
                                icon=ft.Icons.NOTE_ALT,
                                on_click=_save_note,
                                expand=True,
                            ),
                        ),
                    ],
                    run_spacing=6,
                    spacing=8,
                ),
            ],
            spacing=8,
        )

        cards_column.controls.append(
            ft.Container(
                width=min(980, max(300, int(sw * (0.96 if mobile else 0.82)))),
                content=ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=10 if mobile else 12,
                        height=min(780, max(360, int(sh * (0.72 if mobile else 0.78)))),
                        content=ft.Column(
                            [
                                ft.Column(question_content_controls, spacing=8, scroll=ft.ScrollMode.AUTO, expand=True),
                                ft.Divider(height=1, color=_soft_border(dark, 0.12)),
                                action_section,
                            ],
                            spacing=8,
                            expand=True,
                        ),
                    ),
                ),
            )
        )
        contador_text.value = f"{len(questoes)} questoes prontas"
        _update_session_meta()
        _render_mapa_prova()
        _sanitize_control_texts(cards_column)

    def _confirmar(_=None):
        if not questoes:
            return
        idx = int(max(0, min(len(questoes) - 1, estado.get("current_idx", 0))))
        pergunta = questoes[idx]
        selected = (estado.get("respostas") or {}).get(idx)
        correta_idx = int(pergunta.get("correta_index", pergunta.get("correta", 0)) or 0)
        if selected is None or idx in estado["confirmados"]:
            return
        _track_question_time()
        estado["confirmados"].add(idx)
        if not estado.get("simulado_mode"):
            tentativa_correta = selected == correta_idx
            _persist_question_flags(idx, tentativa_correta)
            status_estudo.value = "Resposta correta." if tentativa_correta else "Resposta incorreta."
        else:
            status_estudo.value = "Resposta registrada para correcao no final."
        _persist_mock_progress()
        # Prefetch para modo continuo
        if page and estado.get("modo_continuo") and len(questoes) - idx <= 2:
            page.run_task(_prefetch_one_async)
        _rebuild_cards()
        if page:
            page.update()

    def _mostrar_etapa_config():
        etapa_text.value = "Etapa 1 de 2: configure e gere"
        config_section.visible = True
        study_section.visible = False
        _sync_resultado_box_visibility()

    def _mostrar_etapa_estudo():
        if not questoes:
            _mostrar_etapa_config()
            _set_feedback_text(status_text, "Gere questoes para iniciar a resolucao.", "info")
            _refresh_status_boxes()
            return
        etapa_text.value = "Etapa 2 de 2: resolva e corrija"
        config_section.visible = False
        study_section.visible = True
        _sync_resultado_box_visibility()

    async def _prefetch_one_async():
        if not page:
            return
        filtro = estado.get("ultimo_filtro") or {}
        topic = (filtro.get("topic") or "").strip()
        referencia = filtro.get("referencia") or []
        difficulty_key = filtro.get("difficulty") or dificuldade_padrao
        gen_profile = _generation_profile(user, "quiz")
        service = _create_user_ai_service(user, force_economic=bool(gen_profile.get("force_economic")))
        nova = None
        if gen_profile.get("delay_s", 0) > 0:
            await asyncio.sleep(float(gen_profile["delay_s"]))
        if service and (topic or referencia):
            try:
                questao = await asyncio.to_thread(
                    service.generate_quiz,
                    referencia or None,
                    topic or None,
                    DIFICULDADES.get(difficulty_key, {}).get("nome", "Intermediario"),
                    1,
                )
                qnorm = _normalize_question_for_ui(questao) if questao else None
                if qnorm:
                    nova = qnorm
                    if db:
                        try:
                            tema_cache = topic or "Geral"
                            db.salvar_questao_cache(tema_cache, difficulty_key, qnorm)
                        except Exception as ex:
                            log_exception(ex, "main._build_quiz_body.prefetch.salvar_questao_cache")
            except Exception as ex:
                log_exception(ex, "main._build_quiz_body.prefetch")
        if not nova and topic and db:
            try:
                cached = db.listar_questoes_cache(topic, difficulty_key, 1)
                cached = [q for q in (_normalize_question_for_ui(x) for x in cached) if q]
                if cached:
                    nova = cached[0]
            except Exception as ex:
                log_exception(ex, "main._build_quiz_body.prefetch.cache")
        if not nova:
            nova = random.choice(DEFAULT_QUIZ_QUESTIONS)
        if nova:
            questoes.append(dict(nova))
            _set_feedback_text(status_text, f"Modo continuo: +1 questao pronta ({len(questoes)} total).", "info")
            if page:
                page.update()

    def corrigir(_=None, forcar_timeout: bool = False):
        if not questoes:
            status_estudo.value = "Gere questoes antes de corrigir."
            if page:
                page.update()
            return
        if estado["corrigido"] and not bool(estado.get("simulado_mode")):
            return

        total = len(questoes)
        simulado_mode = bool(estado.get("simulado_mode"))
        nao_respondidas = [i for i in range(total) if estado["respostas"].get(i) is None]
        if nao_respondidas and (not simulado_mode):
            status_estudo.value = f"Existem {len(nao_respondidas)} questoes sem resposta."
            if page:
                page.update()
            return

        _track_question_time()
        time_map = dict(estado.get("question_time_ms") or {})
        acertos = 0
        erros = 0
        puladas = 0
        items_report = []
        wrong_questions = []

        for idx, q in enumerate(questoes):
            escolhida = estado["respostas"].get(idx)
            correta = int(q.get("correta_index", q.get("correta", 0)) or 0)
            if escolhida is None:
                puladas += 1
                resultado_item = "skip"
                _persist_question_flags(idx, False)
            elif int(escolhida) == correta:
                acertos += 1
                resultado_item = "correct"
                _persist_question_flags(idx, True)
            else:
                erros += 1
                resultado_item = "wrong"
                wrong_questions.append(q)
                _persist_question_flags(idx, False)

            items_report.append(
                {
                    "ordem": idx + 1,
                    "question": q,
                    "resultado": resultado_item,
                    "resposta_index": (None if escolhida is None else int(escolhida)),
                    "correta_index": int(correta),
                    "tempo_ms": int(time_map.get(idx, 0) or 0),
                    "meta": _question_simulado_meta(q),
                }
            )

        xp = acertos * 10
        db_local = state["db"]
        if state.get("usuario"):
            db_local.registrar_resultado_quiz(state["usuario"]["id"], acertos, total, xp)
            state["usuario"]["xp"] += xp
            state["usuario"]["acertos"] += acertos
            state["usuario"]["total_questoes"] += total
            try:
                progresso = db_local.obter_progresso_diario(state["usuario"]["id"])
                state["usuario"]["streak_dias"] = int(progresso.get("streak_dias", state["usuario"].get("streak_dias", 0)))
            except Exception:
                pass

        # Simulado: persistencia de itens + finalizacao + relatorio
        if simulado_mode and db_local and user.get("id"):
            _cancel_timer_task()
            _ensure_mock_exam_session(total)
            sid = int(estado.get("mock_exam_session_id") or 0)
            if sid > 0:
                try:
                    for item in items_report:
                        db_local.registrar_mock_exam_item(
                            session_id=sid,
                            ordem=int(item["ordem"]),
                            question=dict(item["question"]),
                            meta=dict(item["meta"] or {}),
                            resposta_index=item["resposta_index"],
                            correta_index=item["correta_index"],
                            tempo_ms=int(item.get("tempo_ms") or 0),
                        )
                    tempo_total_s = 0
                    if estado.get("mock_exam_started_at"):
                        tempo_total_s = int(max(0, time.monotonic() - float(estado.get("mock_exam_started_at"))))
                    elif estado.get("start_time"):
                        tempo_total_s = int(max(0, time.monotonic() - float(estado.get("start_time"))))
                    score_pct = (acertos / max(1, total)) * 100.0
                    db_local.finalizar_mock_exam_session(
                        sid,
                        acertos=acertos,
                        erros=erros,
                        puladas=puladas,
                        score_pct=score_pct,
                        tempo_gasto_s=tempo_total_s,
                    )
                except Exception as ex:
                    log_exception(ex, "main._build_quiz_body.corrigir.finalizar_mock_exam")

            report = MockExamReportService.summarize_items(items_report)
            estado["simulado_items"] = list(items_report)
            estado["simulado_report"] = dict(report)

            def _review_wrong(_=None):
                if not wrong_questions:
                    _set_feedback_text(status_estudo, "Sem questoes erradas para revisar.", "info")
                    _refresh_status_boxes()
                    if page:
                        page.update()
                    return
                questoes[:] = [
                    dict(qn)
                    for qn in (_normalize_question_for_ui(q) for q in wrong_questions)
                    if qn
                ]
                _reset_mock_exam_runtime(clear_mode=True)
                estado["current_idx"] = 0
                estado["respostas"] = {}
                estado["confirmados"] = set()
                estado["corrigido"] = False
                estado["question_last_ts"] = time.monotonic()
                resultado.value = ""
                _sync_resultado_box_visibility()
                _set_feedback_text(status_estudo, "Revisao de erradas iniciada.", "success")
                _rebuild_cards()
                if page:
                    page.update()

            def _add_wrong_to_notebook(_=None):
                if not (db_local and user.get("id") and wrong_questions):
                    _set_feedback_text(status_estudo, "Sem questoes erradas para adicionar.", "info")
                    _refresh_status_boxes()
                    if page:
                        page.update()
                    return
                try:
                    qrepo = QuestionProgressRepository(db_local)
                    for q in wrong_questions:
                        qrepo.register_result(int(user["id"]), q, "mark")
                    _set_feedback_text(status_estudo, "Erradas adicionadas ao caderno de revisao.", "success")
                except Exception as ex:
                    log_exception(ex, "main._build_quiz_body._add_wrong_to_notebook")
                    _set_feedback_text(status_estudo, "Falha ao adicionar erradas ao caderno.", "error")
                _refresh_status_boxes()
                if page:
                    page.update()

            def _flashcards_from_wrong(_=None):
                if not wrong_questions:
                    _set_feedback_text(status_estudo, "Sem questoes erradas para gerar flashcards.", "info")
                    _refresh_status_boxes()
                    if page:
                        page.update()
                    return
                seeds = []
                for q in wrong_questions[:15]:
                    en = str(q.get("enunciado") or q.get("pergunta") or "").strip()
                    alts = q.get("alternativas") or q.get("opcoes") or []
                    try:
                        cidx = int(q.get("correta_index", q.get("correta", 0)) or 0)
                    except Exception:
                        cidx = 0
                    cidx = max(0, min(cidx, max(0, len(alts) - 1)))
                    correta_txt = str(alts[cidx] if alts else "").strip()
                    if en and correta_txt:
                        seeds.append({"frente": en, "verso": correta_txt, "tema": str(q.get("tema") or topic_field.value or "Geral")})
                state["flashcards_seed_cards"] = seeds
                navigate("/flashcards")

            def _metric_block(title: str, value: str, color: str) -> ft.Control:
                return ds_card(
                    dark=dark,
                    padding=DS.SP_10,
                    content=ft.Column(
                        [
                            ft.Text(title, size=11, color=DS.text_sec_color(dark)),
                            ft.Text(value, size=17, weight=ft.FontWeight.W_700, color=color),
                        ],
                        spacing=4,
                    ),
                )

            by_disc = report.get("by_disciplina") or {}
            by_ass = report.get("by_assunto") or {}
            score_pct = float(report.get("score_pct") or 0.0)

            disc_controls = [ft.Text("Por disciplina", size=12, weight=ft.FontWeight.W_600, color=_color("texto", dark))]
            for name, stats in list(by_disc.items())[:8]:
                ratio = float(stats.get("acertos", 0)) / max(1, int(stats.get("total", 0)))
                disc_controls.append(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(str(name), size=11, color=_color("texto", dark)),
                                    ft.Container(expand=True),
                                    ft.Text(f"{int(stats.get('acertos', 0))}/{int(stats.get('total', 0))}", size=11, color=_color("texto_sec", dark)),
                                ]
                            ),
                            ds_progress_bar(ratio, dark=dark, color=DS.P_500),
                        ],
                        spacing=4,
                    )
                )
            if len(disc_controls) == 1:
                disc_controls.append(ft.Text("Sem dados de disciplina.", size=11, color=_color("texto_sec", dark)))

            ass_controls = [ft.Text("Por assunto", size=12, weight=ft.FontWeight.W_600, color=_color("texto", dark))]
            for name, stats in list(by_ass.items())[:8]:
                ratio = float(stats.get("acertos", 0)) / max(1, int(stats.get("total", 0)))
                ass_controls.append(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(str(name), size=11, color=_color("texto", dark)),
                                    ft.Container(expand=True),
                                    ft.Text(f"{int(stats.get('acertos', 0))}/{int(stats.get('total', 0))}", size=11, color=_color("texto_sec", dark)),
                                ]
                            ),
                            ds_progress_bar(ratio, dark=dark, color=DS.A_500),
                        ],
                        spacing=4,
                    )
                )
            if len(ass_controls) == 1:
                ass_controls.append(ft.Text("Sem dados de assunto.", size=11, color=_color("texto_sec", dark)))

            simulado_report_column.controls = [
                ds_card(
                    dark=dark,
                    padding=DS.SP_12,
                    content=ft.Column(
                        [
                            ft.Text("Relatorio do Simulado", size=DS.FS_BODY, weight=ft.FontWeight.W_700, color=_color("texto", dark)),
                            ft.ResponsiveRow(
                                [
                                    ft.Container(col={"xs": 6, "md": 3}, content=_metric_block("Score", f"{score_pct:.1f}%", DS.P_500)),
                                    ft.Container(col={"xs": 6, "md": 3}, content=_metric_block("Acertos", str(acertos), DS.SUCESSO)),
                                    ft.Container(col={"xs": 6, "md": 3}, content=_metric_block("Erros", str(erros), DS.ERRO)),
                                    ft.Container(col={"xs": 6, "md": 3}, content=_metric_block("Puladas", str(puladas), DS.WARNING)),
                                ],
                                spacing=8,
                                run_spacing=8,
                            ),
                            ft.Text(
                                f"Tempo total: {int(report.get('tempo_total_s', 0))}s | Tempo medio: {int(report.get('tempo_medio_s', 0))}s",
                                size=11,
                                color=_color("texto_sec", dark),
                            ),
                            ds_divider(dark),
                            ft.Column(disc_controls, spacing=6),
                            ds_divider(dark),
                            ft.Column(ass_controls, spacing=6),
                            ft.Row(
                                [
                                    ds_btn_primary("Revisar erradas", on_click=_review_wrong, dark=dark, icon=ft.Icons.AUTO_FIX_HIGH),
                                    ds_btn_secondary("Adicionar erradas ao caderno", on_click=_add_wrong_to_notebook, dark=dark),
                                    ds_btn_ghost("Gerar flashcards das erradas", on_click=_flashcards_from_wrong, dark=dark, icon=ft.Icons.STYLE_OUTLINED),
                                ],
                                wrap=True,
                                spacing=8,
                            ),
                        ],
                        spacing=8,
                    ),
                )
            ]
            simulado_report_column.visible = True

        taxa = (acertos / max(1, total))
        if not simulado_mode:
            if taxa < 0.6:
                recomendacao_text.value = "Recomendado: revisar erros agora para consolidar base."
                recomendacao_button.text = "Iniciar revisao de erros"
                recomendacao_button.icon = ft.Icons.AUTO_FIX_HIGH
                recomendacao_button.on_click = _quick_due_reviews
            else:
                recomendacao_text.value = "Bom ritmo: avance para nova sessao em nivel igual ou acima."
                recomendacao_button.text = "Nova sessao (progresso)"
                recomendacao_button.icon = ft.Icons.TRENDING_UP
                recomendacao_button.on_click = _quick_new_session
            recomendacao_text.visible = True
            recomendacao_button.visible = True
        else:
            recomendacao_text.visible = False
            recomendacao_button.visible = False

        resultado.value = f"Acertos: {acertos}/{total} | XP ganho: {xp}"
        resultado.color = CORES["sucesso"] if acertos else CORES["erro"]
        _sync_resultado_box_visibility()
        status_estudo.value = "Correcao concluida." if not forcar_timeout else "Tempo esgotado. Simulado corrigido."
        resultado.update()
        estado["corrigido"] = True
        estado["question_last_ts"] = None
        _rebuild_cards()
        if page:
            page.update()

    async def _gerar_quiz_async():
        if not page:
            return
        try:
            dropdown_val = quiz_count_dropdown.value or "10"
            modo_continuo = dropdown_val == "cont"
            estado["modo_continuo"] = modo_continuo
            quantidade = 3 if modo_continuo else int(dropdown_val)
            quantidade = max(1, min(30, quantidade))
        except ValueError:
            quantidade = 10
            estado["modo_continuo"] = False
        generate_button.disabled = True
        carregando.visible = True
        gen_profile = _generation_profile(user, "quiz")
        if gen_profile.get("label") == "free_slow":
            _set_feedback_text(status_text, f"Modo Free: gerando {quantidade} questoes (economico e mais lento)...", "info")
        else:
            _set_feedback_text(status_text, f"Gerando {quantidade} questoes...", "info")
        _refresh_status_boxes()
        page.update()

        difficulty_key = difficulty_dropdown.value or dificuldade_padrao
        topic = (topic_field.value or "").strip()
        advanced_applied = _get_applied_advanced_filters()
        if not topic:
            topic = QuizFilterService.primary_topic(advanced_applied) or topic
        referencia = [line.strip() for line in (referencia_field.value or "").splitlines() if line.strip()]
        referencia = referencia + estado["upload_texts"]
        advanced_hint = QuizFilterService.to_generation_hint(advanced_applied)
        if advanced_hint:
            referencia.append(advanced_hint)
        service = _create_user_ai_service(user, force_economic=bool(gen_profile.get("force_economic")))
        geradas = []
        session_mode = session_mode_dropdown.value or "nova"
        estado["simulado_mode"] = bool(simulado_mode_switch.value)
        estado["feedback_imediato"] = not bool(estado["simulado_mode"])
        _reset_mock_exam_runtime(clear_mode=False)
        mock_exam_policy = MockExamService(db) if db else None
        if estado["simulado_mode"]:
            premium_active = _is_premium_active(user)
            quantidade, capped = MockExamService.normalize_question_count(quantidade, premium_active)
            if capped:
                quiz_count_dropdown.value = str(quantidade)
                preview_count_text.value = str(quantidade)
                _set_feedback_text(
                    status_text,
                    f"Plano Free: simulado limitado a {MockExamService.FREE_MAX_QUESTIONS} questoes.",
                    "warning",
                )
            if (not premium_active) and mock_exam_policy and user.get("id"):
                allowed, _used, _limit = mock_exam_policy.consume_start_today(int(user["id"]), premium=False)
                if not allowed:
                    _set_feedback_text(status_text, "Plano Free: limite diario de simulado atingido.", "warning")
                    _show_upgrade_dialog(page, navigate, "No Premium voce pode fazer simulados ilimitados por dia.")
                    carregando.visible = False
                    generate_button.disabled = False
                    _refresh_status_boxes()
                    page.update()
                    return
            tempo_limite_s = int(max(300, int(estado.get("tempo_limite_s") or (60 * 60))))
            estado["tempo_limite_s"] = tempo_limite_s
            estado["prova_deadline"] = time.monotonic() + tempo_limite_s
        else:
            estado["tempo_limite_s"] = None
        estado["ultimo_filtro"] = {
            "topic": topic,
            "referencia": referencia,
            "difficulty": difficulty_key,
            "advanced_filters": advanced_applied,
            "advanced_hint": advanced_hint,
        }

        if db and user.get("id") and session_mode != "nova":
            try:
                geradas = db.listar_questoes_usuario(user["id"], modo=session_mode, limite=quantidade)
            except Exception as ex:
                log_exception(ex, "main._build_quiz_body.listar_questoes_usuario")

        if gen_profile.get("delay_s", 0) > 0:
            await asyncio.sleep(float(gen_profile["delay_s"]))
        if not geradas and service and (topic or referencia):
            for _ in range(quantidade):
                try:
                    questao = await asyncio.to_thread(
                        service.generate_quiz,
                        referencia or None,
                        topic or None,
                        DIFICULDADES.get(difficulty_key, {}).get("nome", "Intermediario"),
                    )
                    if questao:
                        qnorm = _normalize_question_for_ui(questao)
                        if qnorm:
                            geradas.append(qnorm)
                            if db:
                                try:
                                    tema_cache = topic or "Geral"
                                    db.salvar_questao_cache(tema_cache, difficulty_key, qnorm)
                                except Exception as ex:
                                    log_exception(ex, "main._build_quiz_body.salvar_questao_cache")
                except Exception as ex:
                    log_exception(ex, "main._build_quiz_body")
        if not geradas:
            if topic and db:
                try:
                    geradas = db.listar_questoes_cache(topic, difficulty_key, quantidade)
                    geradas = [q for q in (_normalize_question_for_ui(x) for x in geradas) if q]
                except Exception as ex:
                    log_exception(ex, "main._build_quiz_body.listar_questoes_cache")
                    geradas = []
            if not geradas and topic:
                _set_feedback_text(
                    status_text,
                    "Sem material offline dessa materia ainda. Tente gerar essa materia com IA quando houver cota.",
                    "warning",
                )
                if _is_ai_quota_exceeded(service):
                    _show_quota_dialog(page, navigate)
                carregando.visible = False
                generate_button.disabled = False
                page.update()
                return
            if not geradas:
                if quantidade <= len(DEFAULT_QUIZ_QUESTIONS):
                    geradas = random.sample(DEFAULT_QUIZ_QUESTIONS, quantidade)
                else:
                    geradas = [random.choice(DEFAULT_QUIZ_QUESTIONS) for _ in range(quantidade)]
            if _is_ai_quota_exceeded(service):
                _set_feedback_text(status_text, f"Cotas da IA esgotadas. Modo offline: {len(geradas)} questoes prontas.", "warning")
                _show_quota_dialog(page, navigate)
            else:
                _set_feedback_text(status_text, f"Modo offline: {len(geradas)} questoes prontas.", "info")
        else:
            while len(geradas) < quantidade:
                geradas.append(random.choice(DEFAULT_QUIZ_QUESTIONS))
            if session_mode == "nova":
                _set_feedback_text(status_text, f"IA: {len(geradas)} questoes geradas.", "success")
            else:
                _set_feedback_text(status_text, f"Sessao rapida ({session_mode}): {len(geradas)} questoes.", "success")
        _refresh_status_boxes()

        geradas_norm = [q for q in (_normalize_question_for_ui(item) for item in geradas) if q]
        if not geradas_norm:
            if quantidade <= len(DEFAULT_QUIZ_QUESTIONS):
                geradas_norm = [dict(q) for q in random.sample(DEFAULT_QUIZ_QUESTIONS, quantidade)]
            else:
                geradas_norm = [dict(random.choice(DEFAULT_QUIZ_QUESTIONS)) for _ in range(quantidade)]
        questoes[:] = [dict(q) for q in geradas_norm]
        estado["current_idx"] = 0
        estado["respostas"].clear()
        estado["corrigido"] = False
        estado["confirmados"] = set()
        estado["start_time"] = time.monotonic()
        estado["question_time_ms"] = {}
        estado["question_last_ts"] = time.monotonic()
        resultado.value = ""
        _sync_resultado_box_visibility()
        recomendacao_text.visible = False
        recomendacao_button.visible = False
        status_estudo.value = ""
        _refresh_status_boxes()
        estado["favoritas"] = set()
        estado["marcadas_erro"] = set()

        if db and user.get("id"):
            for idx, q in enumerate(questoes):
                meta = q.get("_meta") or {}
                if meta.get("favorita"):
                    estado["favoritas"].add(idx)
                if meta.get("marcado_erro"):
                    estado["marcadas_erro"].add(idx)
                _persist_question_flags(idx, None)

        if bool(estado.get("simulado_mode")):
            _ensure_mock_exam_session(len(questoes))
            _cancel_timer_task()
            timer_ref["token"] = int(timer_ref.get("token") or 0) + 1
            if page:
                try:
                    timer_ref["task"] = page.run_task(_cronometro_task, int(timer_ref["token"]))
                except Exception as ex:
                    log_exception(ex, "main._build_quiz_body.start_timer")

        _rebuild_cards()
        _mostrar_etapa_estudo()
        carregando.visible = False
        generate_button.disabled = False
        page.update()

    def _on_gerar_clique(e):
        if not page:
            return
        page.run_task(_gerar_quiz_async)

    def limpar_respostas(_):
        if not questoes:
            _set_feedback_text(status_text, "Ainda nao ha questoes para limpar.", "info")
            _mostrar_etapa_config()
            _refresh_status_boxes()
            if page:
                page.update()
            return
        estado["respostas"].clear()
        estado["corrigido"] = False
        resultado.value = ""
        _sync_resultado_box_visibility()
        recomendacao_text.visible = False
        recomendacao_button.visible = False
        estado["confirmados"] = set()
        _reset_mock_exam_runtime(clear_mode=False)
        estado["question_time_ms"] = {}
        estado["question_last_ts"] = time.monotonic()
        status_estudo.value = "Respostas limpas."
        _refresh_status_boxes()
        _rebuild_cards()
        if page:
            page.update()

    def _voltar_config(_):
        _mostrar_etapa_config()
        if page:
            page.update()

    generate_button = ft.ElevatedButton(
        "Gerar e iniciar estudo",
        icon=ft.Icons.BOLT,
        on_click=_on_gerar_clique,
        style=ft.ButtonStyle(bgcolor=CORES["primaria"], color="white"),
    )

    advanced_visible = {"value": False}
    advanced_button = ft.TextButton("Mostrar ajustes avancados", icon=ft.Icons.TUNE)

    def _toggle_advanced(_):
        advanced_visible["value"] = not advanced_visible["value"]
        advanced_section.visible = advanced_visible["value"]
        advanced_button.text = "Ocultar ajustes avancados" if advanced_visible["value"] else "Mostrar ajustes avancados"
        if page:
            page.update()

    advanced_button.on_click = _toggle_advanced

    def _quick_new_session(_):
        session_mode_dropdown.value = "nova"
        simulado_mode_switch.value = False
        _sync_feedback_policy_ui()
        quiz_count_dropdown.value = "10"
        preview_count_text.value = "10"
        _reset_mock_exam_runtime(clear_mode=True)
        _set_feedback_text(status_text, "Modo treino rapido selecionado.", "info")
        if page:
            page.update()
        _on_gerar_clique(None)

    def _quick_due_reviews(_):
        session_mode_dropdown.value = "erradas"
        simulado_mode_switch.value = False
        _sync_feedback_policy_ui()
        quiz_count_dropdown.value = "10"
        preview_count_text.value = "10"
        _reset_mock_exam_runtime(clear_mode=True)
        _set_feedback_text(status_text, "Modo revisao de erros selecionado.", "info")
        if page:
            page.update()
        _on_gerar_clique(None)

    def _quick_simulado(_):
        session_mode_dropdown.value = "nova"
        simulado_mode_switch.value = True
        _sync_feedback_policy_ui()
        quiz_count_dropdown.value = "30"
        preview_count_text.value = "30"
        _reset_mock_exam_runtime(clear_mode=False)
        estado["tempo_limite_s"] = 60 * 60
        _set_feedback_text(status_text, "Modo prova selecionado.", "info")
        if page:
            page.update()
        _on_gerar_clique(None)

    advanced_section = ft.Column(
        [
            ft.Row(
                [
                    difficulty_dropdown,
                    session_mode_dropdown,
                    simulado_mode_switch,
                    feedback_policy_text,
                    ft.Text("Questoes encontradas:"),
                    preview_count_text,
                ],
                wrap=True,
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            referencia_field,
            ft.Row(
                [
                    ft.ElevatedButton("Anexar material", icon=ft.Icons.UPLOAD_FILE, on_click=_upload_material),
                    library_dropdown,
                    ft.TextButton("Limpar material", on_click=_limpar_material),
                    upload_info,
                ],
                wrap=True,
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Row(
                [
                    save_filter_name,
                    ft.ElevatedButton("Salvar filtro", icon=ft.Icons.SAVE, on_click=_save_current_filter),
                    saved_filters_dropdown,
                    ft.TextButton("Excluir", icon=ft.Icons.DELETE_OUTLINE, on_click=_delete_selected_filter),
                ],
                wrap=True,
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        spacing=10,
        visible=False,
    )

    config_section = ft.Column(
        [
            ft.Card(
                elevation=1,
                content=ft.Container(
                    padding=14,
                    content=ft.Column(
                        [
                            ft.Text("Inicie sua sessao de estudo", size=18, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                            ft.ResponsiveRow(
                                [
                                    ft.Container(content=topic_field, col={"sm": 12, "md": 8}),
                                    ft.Container(content=quiz_count_dropdown, col={"sm": 12, "md": 4}),
                                ],
                                spacing=12,
                                run_spacing=8,
                            ),
                            ft.ResponsiveRow(
                                [
                                    ft.Container(content=advanced_filters_button, col={"xs": 12, "md": 5}),
                                    ft.Container(content=advanced_filters_hint, col={"xs": 12, "md": 7}),
                                ],
                                spacing=10,
                                run_spacing=6,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.ResponsiveRow(
                                [
                                    ft.Container(
                                        col={"xs": 12, "md": 4},
                                        content=ft.ElevatedButton(
                                            "Treino rapido",
                                            icon=ft.Icons.PLAY_CIRCLE_FILL,
                                            on_click=_quick_new_session,
                                            expand=True,
                                        ),
                                    ),
                                    ft.Container(
                                        col={"xs": 12, "md": 4},
                                        content=ft.OutlinedButton(
                                            "Revisar erros",
                                            icon=ft.Icons.AUTO_FIX_HIGH,
                                            on_click=_quick_due_reviews,
                                            expand=True,
                                        ),
                                    ),
                                    ft.Container(
                                        col={"xs": 12, "md": 4},
                                        content=ft.OutlinedButton(
                                            "Modo prova",
                                            icon=ft.Icons.TIMER,
                                            on_click=_quick_simulado,
                                            expand=True,
                                        ),
                                    ),
                                ],
                                run_spacing=6,
                                spacing=10,
                            ),
                            advanced_button,
                            advanced_section,
                            ft.ResponsiveRow(
                                [
                                    ft.Container(col={"xs": 12, "md": 4}, content=generate_button),
                                    ft.Container(col={"xs": 12, "md": 8}, content=ft.Row([carregando, ft.Container(content=status_box, expand=True)], spacing=10, wrap=True)),
                                ],
                                run_spacing=6,
                                spacing=10,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        ],
                        spacing=10,
                    ),
                ),
            )
        ],
        spacing=12,
        visible=True,
    )

    study_section = ft.Column(
        [
            ft.Row(
                [
                    ft.Text("Resolva as questoes", size=18, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                    ft.Row([contador_text, progresso_text, tempo_text], spacing=10, wrap=True),
                ],
                wrap=True,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            filtro_resumo_text,
            status_estudo_box,
            mapa_prova_container,
            cards_column,
            resultado_box,
            ft.Row([recomendacao_text, recomendacao_button], wrap=True, spacing=10),
            ft.ResponsiveRow(
                [
                    ft.Container(
                        col={"xs": 12, "md": 4},
                        content=ft.ElevatedButton("Corrigir", icon=ft.Icons.CHECK, on_click=corrigir, expand=True),
                    ),
                    ft.Container(
                        col={"xs": 12, "md": 8},
                        content=ft.Row(
                            [
                                ft.TextButton("Limpar respostas", icon=ft.Icons.RESTART_ALT, on_click=limpar_respostas),
                                ft.TextButton("Voltar para configuracao", icon=ft.Icons.ARROW_BACK, on_click=_voltar_config),
                                ft.TextButton("Voltar ao Inicio", icon=ft.Icons.HOME_OUTLINED, on_click=lambda _: navigate("/home")),
                            ],
                            wrap=True,
                            spacing=10,
                        ),
                    ),
                ],
                run_spacing=6,
                spacing=10,
            ),
            simulado_report_column,
        ],
        spacing=12,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        visible=False,
    )

    _load_saved_filters()
    _refresh_filter_summary()
    _set_upload_info()
    _rebuild_cards()
    if isinstance(package_questions, list) and package_questions:
        questoes[:] = [
            dict(qn)
            for qn in (_normalize_question_for_ui(q) for q in package_questions)
            if qn
        ]
        estado["current_idx"] = 0
        estado["respostas"].clear()
        estado["corrigido"] = False
        estado["start_time"] = time.monotonic()
        status_estudo.value = "Sessao carregada de pacote da Biblioteca."
        _rebuild_cards()
        _mostrar_etapa_estudo()

    retorno = _wrap_study_content(
        ft.Column(
            [
                _build_focus_header("Questoes", "Fluxo: 1) Configure  2) Gere  3) Responda e corrija", etapa_text, dark),
                config_section,
                study_section,
            ],
            spacing=12,
            expand=True,
        ),
        dark,
    )

    if not ai_enabled:
        status_text.value = "Configure uma API key em Configuracoes para desbloquear a IA."
    return retorno




def _build_flashcards_body(state, navigate, dark: bool):
    page = state.get("page")
    screen_w = _screen_width(page) if page else 1280
    compact = screen_w < 1000
    very_compact = screen_w < 760
    field_w_small = max(140, min(220, int(screen_w - 120)))
    user = state.get("usuario") or {}
    db = state.get("db")
    library_service = LibraryService(db) if db else None
    seed_cards = state.pop("flashcards_seed_cards", None)
    estado = {
        "upload_texts": [],
        "upload_names": [],
        "current_idx": 0,
        "mostrar_verso": False,
        "lembrei": 0,
        "rever": 0,
        "modo_continuo": False,
        "cont_theme": "Conceito",
        "cont_base_content": [],
        "cont_prefetching": False,
    }
    flashcards = []
    if isinstance(seed_cards, list) and seed_cards:
        try:
            from core.services.flashcards_service import FlashcardsService
            flashcards = FlashcardsService.normalize_seed_cards(seed_cards)
        except Exception:
            flashcards = []
    flashcards = _sanitize_payload_texts(list(flashcards or []))
    cards_column = ft.Column(
        spacing=12,
        expand=False,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )
    cards_host = ft.Container(
        content=cards_column,
        opacity=1.0,
        scale=1.0,
        animate_opacity=ft.Animation(160, ft.AnimationCurve.EASE_IN_OUT),
        animate_scale=ft.Animation(160, ft.AnimationCurve.EASE_IN_OUT),
    )
    carregando = ft.ProgressRing(width=28, height=28, visible=False)
    status_text = ft.Text("", size=12, weight=ft.FontWeight.W_400, color=_color("texto_sec", dark))
    status_estudo = ft.Text("", size=12, weight=ft.FontWeight.W_400, color=_color("texto_sec", dark))
    contador_flashcards = ft.Text("0 flashcards prontos", size=12, color=_color("texto_sec", dark))
    desempenho_text = ft.Text("Lembrei: 0 | Rever: 0", size=12, color=_color("texto_sec", dark))
    etapa_text = ft.Text("Etapa 1 de 2: configure e gere", size=13, weight=ft.FontWeight.W_500, color=_color("texto_sec", dark))
    upload_info = ft.Text("Nenhum material enviado.", size=12, weight=ft.FontWeight.W_400, color=_color("texto_sec", dark))
    ai_enabled = bool(_create_user_ai_service(user))

    tema_field = ft.TextField(label="Tema principal", hint_text="Ex.: Direito Administrativo", expand=True)
    referencia_field = ft.TextField(
        label="Referencia ou briefing",
        hint_text="Adicione anotacoes, resumo ou instrucoes para guiar a IA.",
        expand=True,
        min_lines=3,
        max_lines=5,
        multiline=True,
    )
    quantidade_dropdown = ft.Dropdown(
        label="Quantidade",
        width=field_w_small if compact else 160,
        options=[
            ft.dropdown.Option(key="5", text="5 cards"),
            ft.dropdown.Option(key="10", text="10 cards"),
            ft.dropdown.Option(key="cont", text="Continuo"),
        ],
        value="5",
    )
    library_files = []
    if library_service and user.get("id"):
        try:
            library_files = library_service.listar_arquivos(user["id"])
        except Exception as ex:
            log_exception(ex, "main._build_flashcards_body.listar_arquivos")
    library_dropdown = ft.Dropdown(
        label="Adicionar da Biblioteca",
        width=field_w_small if compact else 300,
        options=[ft.dropdown.Option(str(f["id"]), text=str(f["nome_arquivo"])) for f in library_files],
        disabled=not library_files,
    )

    def _set_upload_info():
        names = estado["upload_names"]
        if not names:
            upload_info.value = "Nenhum material enviado."
            return
        preview = ", ".join(names[:3])
        if len(names) > 3:
            preview += f" +{len(names) - 3}"
        upload_info.value = f"{len(names)} arquivo(s): {preview}"

    def _on_library_select(e):
        fid = getattr(e.control, "value", None)
        if not fid or not library_service:
            return
        try:
            texto = library_service.get_conteudo_arquivo(int(fid))
        except Exception as ex:
            log_exception(ex, "main._build_flashcards_body.library_select")
            texto = ""
        if texto:
            nome = next((str(f.get("nome_arquivo") or "Arquivo Biblioteca") for f in library_files if str(f.get("id")) == str(fid)), "Arquivo Biblioteca")
            estado["upload_texts"].append(texto)
            estado["upload_names"].append(f"[LIB] {nome}")
            _set_upload_info()
            _set_feedback_text(status_text, f"Adicionado da biblioteca: {nome}", "success")
        e.control.value = None
        try:
            e.control.update()
        except Exception:
            pass
        if page:
            page.update()

    library_dropdown.on_change = _on_library_select

    async def _pick_files_async():
        if not page:
            return
        _set_feedback_text(status_text, "Abrindo seletor de arquivos...", "info")
        page.update()
        file_paths = await _pick_study_files(page)
        if not file_paths:
            _set_feedback_text(status_text, "Selecao cancelada.", "info")
            page.update()
            return
        upload_texts, upload_names = _extract_uploaded_material(file_paths)
        estado["upload_texts"] = upload_texts
        estado["upload_names"] = upload_names
        if not upload_texts:
            _set_feedback_text(status_text, "Arquivos sem texto legivel. Use PDF/TXT/MD.", "warning")
        else:
            _set_feedback_text(status_text, f"Material carregado: {len(upload_texts)} arquivo(s).", "success")
        _set_upload_info()
        page.update()

    def _upload_material(_):
        if not page:
            return
        page.run_task(_pick_files_async)

    def _limpar_material(_):
        estado["upload_texts"] = []
        estado["upload_names"] = []
        _set_upload_info()
        _set_feedback_text(status_text, "Material removido.", "info")
        if page:
            page.update()

    def _mostrar_etapa_config():
        etapa_text.value = "Etapa 1 de 2: configure e gere"
        config_section.visible = True
        study_section.visible = False

    def _mostrar_etapa_estudo():
        etapa_text.value = "Etapa 2 de 2: revise os flashcards"
        config_section.visible = False
        study_section.visible = True

    def _render_flashcards():
        cards_column.controls.clear()
        screen = (_screen_width(page) if page else 1280)
        screen_h = (_screen_height(page) if page else 820)
        is_compact = screen < 1000
        title_font = 22 if screen < 900 else (26 if screen < 1280 else 30)
        card_w = min(560, max(280, int(screen * (0.90 if screen < 760 else (0.58 if is_compact else 0.50)))))
        # Mantem os botoes visiveis: limita altura do card conforme viewport.
        card_h = min(420, max(250, int(screen_h * (0.46 if is_compact else 0.52))))
        if not flashcards:
            cards_column.controls.append(
                ft.Container(
                    width=card_w,
                    padding=14,
                    border_radius=10,
                    bgcolor=_color("card", dark),
                    content=ft.Text("Nenhum flashcard carregado.", color=_color("texto_sec", dark)),
                )
            )
            contador_flashcards.value = "0 flashcards prontos"
            desempenho_text.value = "Lembrei: 0 | Rever: 0"
            return

        idx = int(max(0, min(len(flashcards) - 1, estado["current_idx"])))
        estado["current_idx"] = idx
        card = dict(flashcards[idx]) if isinstance(flashcards[idx], dict) else {}
        frente = _fix_mojibake_text(str(card.get("frente", "")))
        verso = _fix_mojibake_text(str(card.get("verso", "")))
        revelou = bool(estado["mostrar_verso"])
        if dark:
            card_bg = "#111827" if not revelou else "#1F2937"
            inner_bg = "#0F172A" if not revelou else "#111827"
        else:
            card_bg = "#DDE2EC" if not revelou else "#FFFFFF"
            inner_bg = "#D1D7E3" if not revelou else "#F3F4F6"

        cards_column.controls.append(
            ft.Container(
                width=card_w,
                height=card_h,
                border_radius=18,
                border=ft.border.all(1, _soft_border(dark, 0.10)),
                bgcolor=card_bg,
                shadow=ft.BoxShadow(
                    blur_radius=26,
                    spread_radius=1,
                    color=ft.Colors.with_opacity(0.14, "#000000"),
                ),
                padding=18,
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(f"Card {idx + 1}/{len(flashcards)}", size=12, color=_color("texto_sec", dark)),
                                ft.Container(
                                    padding=ft.padding.symmetric(horizontal=10, vertical=4),
                                    border_radius=999,
                                    bgcolor=ft.Colors.with_opacity(0.14, CORES["primaria"]),
                                    content=ft.Text("Verso" if revelou else "Frente", size=11, weight=ft.FontWeight.W_600, color=CORES["primaria"]),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Container(
                            expand=not revelou,
                            padding=16,
                            border_radius=12,
                            bgcolor=inner_bg,
                            content=ft.Column(
                                [
                                    ft.Container(
                                        expand=not revelou,
                                        alignment=ft.Alignment(0, 0),
                                        content=ft.Text(
                                            frente,
                                            size=(17 if very_compact else title_font),
                                            weight=ft.FontWeight.BOLD,
                                            color=_color("texto", dark),
                                            text_align=ft.TextAlign.LEFT if very_compact else ft.TextAlign.CENTER,
                                        ),
                                    ),
                                    ft.Container(expand=not revelou),
                                    ft.Container(
                                        visible=bool(estado["mostrar_verso"]),
                                        padding=12,
                                        border_radius=10,
                                        bgcolor=ft.Colors.with_opacity(0.10, CORES["primaria"]),
                                        content=ft.Column(
                                            [
                                                ft.Text("Resposta", size=11, weight=ft.FontWeight.W_600, color=CORES["primaria"]),
                                                ft.Text(verso, color=_color("texto", dark), text_align=ft.TextAlign.LEFT if very_compact else ft.TextAlign.CENTER),
                                            ],
                                            spacing=6,
                                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                        ),
                                    ),
                                ],
                                spacing=10,
                            ),
                        ),
                    ],
                    spacing=12,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
        )
        if estado.get("modo_continuo"):
            contador_flashcards.value = f"{len(flashcards)} flashcards (modo continuo)"
        else:
            contador_flashcards.value = f"{len(flashcards)} flashcards prontos"
        desempenho_text.value = f"Lembrei: {estado['lembrei']} | Rever: {estado['rever']}"
        _sanitize_control_texts(cards_column)

    async def _animate_card_transition(mutator):
        if page:
            cards_host.opacity = 0.0
            cards_host.scale = 0.97
            page.update()
            await asyncio.sleep(0.10)
        mutator()
        _render_flashcards()
        if page:
            cards_host.opacity = 1.0
            cards_host.scale = 1.0
            page.update()

    def _prev_card(_=None):
        if not flashcards:
            return
        if estado.get("modo_continuo"):
            estado["current_idx"] = (estado["current_idx"] - 1) % max(1, len(flashcards))
        else:
            estado["current_idx"] = max(0, estado["current_idx"] - 1)
        estado["mostrar_verso"] = False
        _render_flashcards()
        if page:
            page.update()

    def _next_card(_=None):
        if not flashcards:
            return
        if estado.get("modo_continuo"):
            estado["current_idx"] = (estado["current_idx"] + 1) % max(1, len(flashcards))
        else:
            estado["current_idx"] = min(len(flashcards) - 1, estado["current_idx"] + 1)
        estado["mostrar_verso"] = False
        _render_flashcards()
        _maybe_prefetch_more()
        if page:
            page.update()

    def _mostrar_resposta(_=None):
        estado["mostrar_verso"] = True
        _render_flashcards()
        if page:
            page.update()

    def _registrar_avaliacao(lembrei: bool):
        if not flashcards:
            return
        if lembrei:
            estado["lembrei"] += 1
        else:
            estado["rever"] += 1
        if db and user.get("id"):
            try:
                db.registrar_progresso_diario(user["id"], flashcards=1)
            except Exception as ex:
                log_exception(ex, "main._build_flashcards_body._registrar_avaliacao")
        if estado.get("modo_continuo"):
            estado["current_idx"] = (estado["current_idx"] + 1) % max(1, len(flashcards))
        elif estado["current_idx"] < len(flashcards) - 1:
            estado["current_idx"] += 1
        estado["mostrar_verso"] = False
        status_estudo.value = "Card marcado como dominado." if lembrei else "Card marcado para revisar."
        _render_flashcards()
        _maybe_prefetch_more()
        if page:
            page.update()

    def _mark_lembrei(_=None):
        _registrar_avaliacao(True)

    def _mark_rever(_=None):
        _registrar_avaliacao(False)

    async def _prev_card_animated():
        if not flashcards:
            return
        await _animate_card_transition(lambda: (
            estado.__setitem__("current_idx", max(0, estado["current_idx"] - 1)),
            estado.__setitem__("mostrar_verso", False),
        ))

    async def _next_card_animated():
        if not flashcards:
            return
        if estado.get("modo_continuo"):
            await _animate_card_transition(lambda: (
                estado.__setitem__("current_idx", (estado["current_idx"] + 1) % max(1, len(flashcards))),
                estado.__setitem__("mostrar_verso", False),
            ))
        else:
            await _animate_card_transition(lambda: (
                estado.__setitem__("current_idx", min(len(flashcards) - 1, estado["current_idx"] + 1)),
                estado.__setitem__("mostrar_verso", False),
            ))
        _maybe_prefetch_more()

    async def _prefetch_more_flashcards_async():
        if not page:
            return
        if not estado.get("modo_continuo") or estado.get("cont_prefetching"):
            return
        estado["cont_prefetching"] = True
        tema = str(estado.get("cont_theme") or "Conceito").strip() or "Conceito"
        base_content = list(estado.get("cont_base_content") or [])
        if not base_content and tema:
            base_content = [tema]
        prefetch_qtd = 5
        profile = _generation_profile(user, "flashcards")
        service = _create_user_ai_service(user, force_economic=bool(profile.get("force_economic")))
        novos = []
        try:
            if service and base_content:
                try:
                    novos = await asyncio.to_thread(service.generate_flashcards, base_content, prefetch_qtd)
                except Exception as ex:
                    log_exception(ex, "main._build_flashcards_body.prefetch")
            if not novos:
                base_idx = len(flashcards)
                novos = [
                    {
                        "frente": f"{tema} {base_idx + i + 1}",
                        "verso": f"Resumo ou dica sobre {tema} ({base_idx + i + 1}).",
                    }
                    for i in range(prefetch_qtd)
                ]
            novos = _sanitize_payload_texts(list(novos or []))
            novos = [dict(card) for card in novos if isinstance(card, dict)]
            if novos:
                flashcards.extend(novos)
                _render_flashcards()
                if page:
                    page.update()
        finally:
            estado["cont_prefetching"] = False

    def _maybe_prefetch_more():
        if not (page and estado.get("modo_continuo")):
            return
        if estado.get("cont_prefetching"):
            return
        total = len(flashcards)
        idx = int(estado.get("current_idx") or 0)
        if total > 0 and (total - idx) <= 3:
            page.run_task(_prefetch_more_flashcards_async)

    async def _mostrar_resposta_animated():
        if not flashcards or estado["mostrar_verso"]:
            return
        await _animate_card_transition(lambda: estado.__setitem__("mostrar_verso", True))

    def _prev_card_click(_):
        if page:
            page.run_task(_prev_card_animated)
        else:
            _prev_card()

    def _next_card_click(_):
        if page:
            page.run_task(_next_card_animated)
        else:
            _next_card()

    def _mostrar_resposta_click(_):
        if page:
            page.run_task(_mostrar_resposta_animated)
        else:
            _mostrar_resposta()

    async def _gerar_flashcards_async():
        if not page:
            return
        gerar_button.disabled = True
        carregando.visible = True
        pre_profile = _generation_profile(user, "flashcards")
        if pre_profile.get("label") == "free_slow":
            _set_feedback_text(status_text, "Modo Free: gerando flashcards (economico e mais lento)...", "info")
        else:
            _set_feedback_text(status_text, "Gerando flashcards...", "info")
        page.update()

        try:
            modo_continuo = (quantidade_dropdown.value == "cont")
            quantidade = 20 if modo_continuo else max(1, min(10, int(quantidade_dropdown.value or "5")))
        except ValueError:
            quantidade = 5
            modo_continuo = False
        estado["modo_continuo"] = bool(modo_continuo)

        tema = (tema_field.value or "Conceito").strip()
        referencia = [line.strip() for line in (referencia_field.value or "").splitlines() if line.strip()]
        base_content = referencia + estado["upload_texts"]
        if not base_content and tema:
            base_content = [tema]
        estado["cont_theme"] = tema or "Conceito"
        estado["cont_base_content"] = list(base_content)
        estado["cont_prefetching"] = False
        gen_profile = pre_profile
        service = _create_user_ai_service(user, force_economic=bool(gen_profile.get("force_economic")))
        gerados = []

        if gen_profile.get("delay_s", 0) > 0:
            await asyncio.sleep(float(gen_profile["delay_s"]))
        if service and base_content:
            try:
                gerados = await asyncio.to_thread(service.generate_flashcards, base_content, quantidade)
            except Exception as ex:
                log_exception(ex, "main._build_flashcards_body")
        if not gerados:
            base = tema or "Conceito"
            gerados = [
                {"frente": f"{base} {i+1}", "verso": f"Resumo ou dica do {base} {i+1}."}
                for i in range(quantidade)
            ]
            if _is_ai_quota_exceeded(service):
                _set_feedback_text(status_text, "Cotas da IA esgotadas. Flashcards offline prontos.", "warning")
                _show_quota_dialog(page, navigate)
            else:
                _set_feedback_text(status_text, "Flashcards offline prontos.", "info")
        else:
            _set_feedback_text(status_text, f"{len(gerados)} flashcards gerados com IA.", "success")
        gerados = _sanitize_payload_texts(list(gerados or []))
        flashcards[:] = [dict(card) for card in gerados if isinstance(card, dict)]
        estado["current_idx"] = 0
        estado["mostrar_verso"] = False
        estado["lembrei"] = 0
        estado["rever"] = 0
        _render_flashcards()
        _maybe_prefetch_more()
        if estado.get("modo_continuo"):
            status_estudo.value = f"{status_text.value} Modo continuo ativo: novos cards serao adicionados automaticamente."
        else:
            status_estudo.value = status_text.value
        _mostrar_etapa_estudo()
        carregando.visible = False
        gerar_button.disabled = False
        page.update()

    def _on_gerar(e):
        if not page:
            return
        page.run_task(_gerar_flashcards_async)

    def _voltar_config(_):
        _mostrar_etapa_config()
        if page:
            page.update()

    gerar_button = ft.ElevatedButton("Gerar e iniciar revisao", icon=ft.Icons.BOLT, on_click=_on_gerar)

    config_section = ft.Column(
        [
            ft.Card(
                elevation=1,
                content=ft.Container(
                    padding=14,
                    content=ft.Column(
                        [
                            ft.Text("Selecione como deseja gerar os flashcards", size=18, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                            ft.ResponsiveRow(
                                [
                                    ft.Container(content=tema_field, col={"sm": 12, "md": 8}),
                                    ft.Container(content=quantidade_dropdown, col={"sm": 12, "md": 4}),
                                ],
                                spacing=12,
                                run_spacing=8,
                            ),
                            referencia_field,
                            ft.ResponsiveRow(
                                [
                                    ft.Container(
                                        col={"xs": 12, "md": 4},
                                        content=ft.ElevatedButton("Anexar material", icon=ft.Icons.UPLOAD_FILE, on_click=_upload_material, expand=True),
                                    ),
                                    ft.Container(col={"xs": 12, "md": 4}, content=library_dropdown),
                                    ft.Container(
                                        col={"xs": 6, "md": 2},
                                        content=ft.TextButton("Biblioteca", icon=ft.Icons.LOCAL_LIBRARY_OUTLINED, on_click=lambda _: navigate("/library")),
                                    ),
                                    ft.Container(
                                        col={"xs": 6, "md": 2},
                                        content=ft.TextButton("Limpar material", on_click=_limpar_material),
                                    ),
                                    ft.Container(col={"xs": 12, "md": 12}, content=upload_info),
                                ],
                                run_spacing=6,
                                spacing=10,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.ResponsiveRow(
                                [
                                    ft.Container(col={"xs": 12, "md": 4}, content=gerar_button),
                                    ft.Container(
                                        col={"xs": 12, "md": 8},
                                        content=ft.Row([carregando, ft.Container(content=status_text, expand=True)], spacing=10, wrap=True),
                                    ),
                                ],
                                run_spacing=6,
                                spacing=10,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        ],
                        spacing=10,
                    ),
                ),
            ),
        ],
        spacing=12,
        visible=True,
    )

    study_section = ft.Column(
        [
            ft.Row(
                [
                    ft.Text("Revisao de flashcards", size=18, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                    ft.Row([contador_flashcards, desempenho_text], spacing=10, wrap=True),
                ],
                wrap=True,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            _status_banner(status_estudo, dark),
            ft.Container(
                alignment=ft.Alignment(0, 0),
                content=cards_host,
            ),
            ft.ResponsiveRow(
                [
                    ft.Container(col={"xs": 6, "md": 2}, content=ft.TextButton("Anterior", icon=ft.Icons.CHEVRON_LEFT, on_click=_prev_card_click)),
                    ft.Container(
                        col={"xs": 6, "md": 3},
                        content=ft.OutlinedButton("Mostrar resposta", icon=ft.Icons.VISIBILITY, on_click=_mostrar_resposta_click, expand=True),
                    ),
                    ft.Container(
                        col={"xs": 6, "md": 2},
                        content=ft.ElevatedButton("Lembrei", icon=ft.Icons.CHECK_CIRCLE, on_click=_mark_lembrei, expand=True),
                    ),
                    ft.Container(
                        col={"xs": 6, "md": 2},
                        content=ft.OutlinedButton("Rever", icon=ft.Icons.REFRESH, on_click=_mark_rever, expand=True),
                    ),
                    ft.Container(col={"xs": 12, "md": 3}, content=ft.TextButton("Proximo", icon=ft.Icons.CHEVRON_RIGHT, on_click=_next_card_click)),
                ],
                run_spacing=6,
                spacing=10,
            ),
            ft.ResponsiveRow(
                [
                    ft.Container(
                        col={"xs": 12, "md": 6},
                        content=ft.TextButton("Voltar para configuracao", icon=ft.Icons.ARROW_BACK, on_click=_voltar_config),
                    ),
                    ft.Container(
                        col={"xs": 12, "md": 6},
                        content=ft.TextButton("Voltar ao Inicio", icon=ft.Icons.HOME_OUTLINED, on_click=lambda _: navigate("/home")),
                    ),
                ],
                run_spacing=6,
                spacing=10,
            ),
        ],
        spacing=12,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        visible=False,
    )

    _render_flashcards()

    retorno = _wrap_study_content(
        ft.Column(
            [
                _build_focus_header("Flashcards", "Fluxo: 1) Configure  2) Gere  3) Revise ativamente", etapa_text, dark),
                config_section,
                study_section,
            ],
            spacing=12,
            expand=True,
        ),
        dark,
    )
    if not ai_enabled:
        status_text.value = "Configure uma API key em Configuracoes para liberar a IA."
    return retorno


def _build_open_quiz_body(state, navigate, dark: bool):
    page = state.get("page")
    user = state.get("usuario") or {}
    db = state.get("db")
    backend = state.get("backend")
    service = _create_user_ai_service(user)
    status = ft.Text("", size=12, color=_color("texto_sec", dark))
    pergunta_text = ft.Text("", size=16, weight=ft.FontWeight.BOLD, color=_color("texto", dark), text_align=ft.TextAlign.CENTER)
    gabarito_text = ft.Text("", size=13, color=_color("texto_sec", dark))
    resposta_field = ft.TextField(
        label="Sua resposta",
        multiline=True,
        min_lines=6,
        max_lines=10,
        expand=True,
    )
    tema_field = ft.TextField(label="Tema", hint_text="Ex.: Direito Constitucional", expand=True)
    loading = ft.ProgressRing(width=24, height=24, visible=False)
    estado = {"pergunta": "", "gabarito": "", "contexto_gerado": "", "upload_texts": [], "upload_names": [], "etapa": 1}
    secao_texto = ft.Text("Aguardando pergunta...", size=12, color=_color("texto_sec", dark))
    contexto_gerado_text = ft.Text("", size=13, color=_color("texto_sec", dark), text_align=ft.TextAlign.CENTER)
    upload_info = ft.Text("Nenhum material enviado.", size=12, color=_color("texto_sec", dark))
    etapa_text = ft.Text("Etapa 1 de 2: defina o tema", size=13, color=_color("texto_sec", dark))

    def _set_upload_info():
        names = estado["upload_names"]
        if not names:
            upload_info.value = "Nenhum material enviado."
            return
        preview = ", ".join(names[:3])
        if len(names) > 3:
            preview += f" +{len(names) - 3}"
        upload_info.value = f"{len(names)} arquivo(s): {preview}"

    async def _pick_files_async():
        if not page:
            return
        _set_feedback_text(status, "Abrindo seletor de arquivos...", "info")
        page.update()
        file_paths = await _pick_study_files(page)
        if not file_paths:
            _set_feedback_text(status, "Selecao cancelada.", "info")
            page.update()
            return
        upload_texts, upload_names = _extract_uploaded_material(file_paths)
        estado["upload_texts"] = upload_texts
        estado["upload_names"] = upload_names
        if not upload_texts:
            _set_feedback_text(status, "Arquivos sem texto legivel. Use PDF/TXT/MD.", "warning")
        else:
            _set_feedback_text(status, f"Material carregado: {len(upload_texts)} arquivo(s).", "success")
        _set_upload_info()
        page.update()

    def _upload_material(_):
        if not page:
            return
        page.run_task(_pick_files_async)

    def _limpar_material(_):
        estado["upload_texts"] = []
        estado["upload_names"] = []
        _set_upload_info()
        _set_feedback_text(status, "Material removido.", "info")
        if page:
            page.update()

    def _mostrar_etapa_geracao():
        estado["etapa"] = 1
        etapa_text.value = "Etapa 1 de 2: defina o tema"
        config_section.visible = True
        study_section.visible = False

    def _mostrar_etapa_resposta():
        estado["etapa"] = 2
        etapa_text.value = "Etapa 2 de 2: responda com base no contexto"
        config_section.visible = False
        study_section.visible = True

    async def gerar(_):
        if not page:
            return
        loading.visible = True
        _set_feedback_text(status, "Gerando contexto e pergunta-estopim...", "info")
        page.update()
        tema = (tema_field.value or "").strip() or "Tema livre"
        contexto = [f"Tema central: {tema}"] + estado["upload_texts"]
        pergunta = None
        if service:
            try:
                pergunta = await asyncio.to_thread(service.generate_open_question, contexto, "Medio")
            except Exception as ex:
                log_exception(ex, "main._build_open_quiz_body.generate")
        if not pergunta:
            contexto_gerado = f"Voce esta analisando o tema '{tema}' em um cenario pratico, exigindo argumento claro, exemplos e conclusao."
            pergunta = {
                "pergunta": f"Explique os pontos principais sobre {tema}.",
                "resposta_esperada": f"Resposta esperada com fundamentos, estrutura clara e exemplos sobre {tema}.",
                "contexto": contexto_gerado,
            }
            if _is_ai_quota_exceeded(service):
                _set_feedback_text(status, "Cotas da IA esgotadas. Contexto/pergunta gerados no modo offline.", "warning")
                _show_quota_dialog(page, navigate)
            else:
                _set_feedback_text(status, "Contexto e pergunta gerados no modo offline.", "info")
        else:
            _set_feedback_text(status, "Contexto e pergunta gerados com IA.", "success")
        estado["contexto_gerado"] = (
            pergunta.get("contexto")
            or pergunta.get("cenario")
            or f"Cenario gerado para o tema '{tema}'."
        )
        estado["contexto_gerado"] = _fix_mojibake_text(str(estado["contexto_gerado"] or ""))
        sw = _screen_width(page) if page else 1280
        pergunta_text.size = 20 if sw < 900 else (24 if sw < 1280 else 28)
        estado["pergunta"] = _fix_mojibake_text(str(pergunta.get("pergunta", "") or ""))
        estado["gabarito"] = _fix_mojibake_text(str(pergunta.get("resposta_esperada", "") or ""))
        contexto_gerado_text.value = f"Contexto: {estado['contexto_gerado']}"
        pergunta_text.value = estado["pergunta"]
        gabarito_text.value = f"Gabarito: {estado['gabarito']}"
        secao_texto.value = "Contexto e pergunta prontos."
        resposta_field.value = ""
        _mostrar_etapa_resposta()
        loading.visible = False
        page.update()

    async def corrigir(_):
        if not page:
            return
        if not estado["pergunta"] or not resposta_field.value:
            status.value = "Gere uma pergunta e responda antes de corrigir."
            page.update()
            return
        if (not _is_premium_active(user)) and user.get("id"):
            allowed = True
            _used = 0
            consumed_online = False
            if backend and backend.enabled():
                try:
                    usage = await asyncio.to_thread(backend.consume_usage, _backend_user_id(user), "open_quiz_grade", 1)
                    allowed = bool(usage.get("allowed"))
                    _used = int(usage.get("used") or 0)
                    consumed_online = True
                except Exception as ex:
                    log_exception(ex, "main._build_open_quiz_body.consume_usage_backend")
            if (not consumed_online) and db:
                allowed, _used = db.consumir_limite_diario(user["id"], "open_quiz_grade", 1)
            if not allowed:
                _set_feedback_text(
                    status,
                    "Free: limite diario da dissertativa atingido (1/dia).",
                    "warning",
                )
                _show_upgrade_dialog(page, navigate, "No plano Free voce pode corrigir 1 dissertativa por dia.")
                page.update()
                return
        loading.visible = True
        _set_feedback_text(status, "Corrigindo resposta...", "info")
        page.update()
        feedback = None
        if service:
            try:
                feedback = await asyncio.to_thread(
                    service.grade_open_answer,
                    estado["pergunta"],
                    resposta_field.value,
                    estado["gabarito"],
                )
            except Exception as ex:
                log_exception(ex, "main._build_open_quiz_body.grade")
        if not feedback:
            nota = 80 if len(resposta_field.value.split()) > 40 else 55
            feedback = {
                "nota": nota,
                "correto": nota >= 70,
                "feedback": "Estruture melhor em introducao, desenvolvimento e conclusao para melhorar a nota.",
            }
            if _is_ai_quota_exceeded(service):
                _show_quota_dialog(page, navigate)
        if db and user.get("id"):
            try:
                db.registrar_progresso_diario(user["id"], discursivas=1)
            except Exception as ex:
                log_exception(ex, "main._build_open_quiz_body.registrar_progresso_diario")
        _set_feedback_text(
            status,
            f"Nota: {feedback.get('nota', 0)} | {'Aprovado' if feedback.get('correto') else 'Revisar'}",
            "success" if feedback.get("correto") else "warning",
        )
        feedback_txt = _fix_mojibake_text(str(feedback.get("feedback", "") or ""))
        gabarito_text.value = f"Gabarito: {estado['gabarito']}\n\nFeedback: {feedback_txt}"
        loading.visible = False
        page.update()

    def limpar(_):
        estado["pergunta"] = ""
        estado["gabarito"] = ""
        estado["contexto_gerado"] = ""
        contexto_gerado_text.value = ""
        pergunta_text.value = ""
        gabarito_text.value = ""
        resposta_field.value = ""
        status.value = "Campos limpos."
        secao_texto.value = "Aguardando pergunta..."
        _mostrar_etapa_geracao()
        if page:
            page.update()

    config_section = ft.Card(
        elevation=1,
        content=ft.Container(
            padding=14,
            content=ft.Column(
                [
                    ft.Text("1) Defina o tema", size=18, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                    ft.ResponsiveRow(
                        [
                            ft.Container(content=tema_field, col={"sm": 12, "md": 6}),
                        ]
                    ),
                    ft.Text(
                        "A IA vai gerar automaticamente o contexto e a pergunta-estopim para sua dissertacao.",
                        size=12,
                        color=_color("texto_sec", dark),
                    ),
                    ft.ResponsiveRow(
                        [
                            ft.Container(
                                col={"xs": 12, "md": 4},
                                content=ft.ElevatedButton("Anexar material", icon=ft.Icons.UPLOAD_FILE, on_click=_upload_material, expand=True),
                            ),
                            ft.Container(col={"xs": 12, "md": 8}, content=ft.Row([ft.TextButton("Limpar material", on_click=_limpar_material), upload_info], wrap=True, spacing=10)),
                        ],
                        run_spacing=6,
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.ResponsiveRow(
                        [
                            ft.Container(
                                col={"xs": 12, "md": 4},
                                content=ft.ElevatedButton(
                                    "Gerar contexto e pergunta",
                                    icon=ft.Icons.BOLT,
                                    on_click=lambda e: page.run_task(gerar, e),
                                    expand=True,
                                ),
                            ),
                            ft.Container(col={"xs": 12, "md": 8}, content=ft.Row([loading, status], wrap=True, spacing=10)),
                        ],
                        run_spacing=6,
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=10,
            ),
        ),
    )

    study_section = ft.Column(
        [
            ft.Row(
                [
                    ft.Text("2) Sua resposta", size=18, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                    secao_texto,
                ],
                wrap=True,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Container(alignment=ft.Alignment(0, 0), content=contexto_gerado_text),
            ft.Container(alignment=ft.Alignment(0, 0), content=pergunta_text),
            resposta_field,
            ft.ResponsiveRow(
                [
                    ft.Container(
                        col={"xs": 12, "md": 4},
                        content=ft.ElevatedButton("3) Corrigir", icon=ft.Icons.CHECK, on_click=lambda e: page.run_task(corrigir, e), expand=True),
                    ),
                    ft.Container(
                        col={"xs": 12, "md": 8},
                        content=ft.Row(
                            [
                                ft.TextButton("Limpar", icon=ft.Icons.RESTART_ALT, on_click=limpar),
                                ft.TextButton("Voltar para geracao", icon=ft.Icons.ARROW_BACK, on_click=lambda _: (_mostrar_etapa_geracao(), page.update() if page else None)),
                                ft.TextButton("Voltar ao Inicio", icon=ft.Icons.HOME_OUTLINED, on_click=lambda _: navigate("/home")),
                            ],
                            wrap=True,
                            spacing=10,
                        ),
                    ),
                ],
                run_spacing=6,
                spacing=10,
            ),
            gabarito_text,
        ],
        spacing=10,
        expand=True,
        visible=False,
    )

    return _wrap_study_content(
        ft.Column(
            [
                _build_focus_header("Dissertativo", "Fluxo: 1) Tema  2) Contexto e pergunta  3) Resposta e correcao", etapa_text, dark),
                _status_banner(status, dark),
                config_section,
                study_section,
            ],
            spacing=10,
            expand=True,
        ),
        dark,
    )


def _build_study_plan_body(state, navigate, dark: bool):
    page = state.get("page")
    screen_w = _screen_width(page) if page else 1280
    compact = screen_w < 1000
    very_compact = screen_w < 760
    form_width = max(150, min(360, int(screen_w - 120)))
    user = state.get("usuario") or {}
    db = state.get("db")
    objetivo_field = ft.TextField(label="Objetivo", width=form_width if compact else 360, hint_text="Ex.: Aprovacao TRT, ENEM 2026")
    data_prova_field = ft.TextField(
        label="Data da prova",
        width=max(130, min(180, int(form_width * 0.45))) if compact else 180,
        hint_text="DD/MM/AAAA",
        keyboard_type=ft.KeyboardType.NUMBER,
        max_length=10,
    )
    tempo_diario_field = ft.TextField(label="Tempo diario (min)", width=max(130, min(180, int(form_width * 0.45))) if compact else 180, hint_text="90")
    status_text = ft.Text("", size=12, color=_color("texto_sec", dark))
    loading = ft.ProgressRing(width=22, height=22, visible=False)
    itens_column = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
    dias_semana = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]

    def _on_data_prova_change(e):
        formatted = _format_exam_date_input(getattr(e.control, "value", ""))
        if formatted != getattr(e.control, "value", ""):
            e.control.value = formatted
            e.control.update()

    data_prova_field.on_change = _on_data_prova_change

    def _plan_day_limit(data_prova: str) -> Optional[int]:
        prova_dt = _parse_br_date(data_prova)
        if not prova_dt:
            return None
        today = datetime.date.today()
        delta = (prova_dt - today).days
        if delta < 0:
            return 0
        return max(1, min(7, delta + 1))

    def _normalize_plan_items(raw_items: list, topicos: list[str], tempo_diario: int, limite_dias: int) -> list[dict]:
        itens_norm = []
        for i, item in enumerate(list(raw_items or [])):
            if i >= limite_dias:
                break
            if not isinstance(item, dict):
                continue
            itens_norm.append(
                {
                    "dia": str(item.get("dia") or dias_semana[i]),
                    "tema": str(item.get("tema") or topicos[i % len(topicos)]),
                    "atividade": str(item.get("atividade") or "Questoes + revisao de erros + flashcards"),
                    "duracao_min": int(item.get("duracao_min") or tempo_diario),
                    "prioridade": int(item.get("prioridade") or (1 if i < 3 else 2)),
                }
            )
        while len(itens_norm) < limite_dias:
            i = len(itens_norm)
            itens_norm.append(
                {
                    "dia": dias_semana[i],
                    "tema": topicos[i % len(topicos)],
                    "atividade": "Questoes + revisao de erros + flashcards",
                    "duracao_min": tempo_diario,
                    "prioridade": 1 if i < 3 else 2,
                }
            )
        return itens_norm

    def _render_plan():
        itens_column.controls.clear()
        if not db or not user.get("id"):
            itens_column.controls.append(ft.Text("Usuario nao autenticado.", color=CORES["erro"]))
            return
        data = db.obter_plano_ativo(user["id"])
        plan = data.get("plan")
        itens = data.get("itens") or []
        if not plan:
            itens_column.controls.append(ft.Text("Nenhum plano ativo. Gere um novo plano semanal.", color=_color("texto_sec", dark)))
            return
        itens_column.controls.append(
            ft.Container(
                padding=10,
                border_radius=8,
                bgcolor=_color("card", dark),
                content=ft.Row(
                    [
                        ft.Text(f"Objetivo: {plan.get('objetivo') or '-'}", weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                        ft.Container(expand=True),
                        ft.Text(f"Prova: {plan.get('data_prova') or '-'}", size=12, color=_color("texto_sec", dark)),
                    ]
                ),
            )
        )
        for item in itens:
            def _mk_toggle(iid):
                def _on_change(e):
                    if not db:
                        return
                    db.marcar_item_plano(iid, bool(e.control.value))
                    _render_plan()
                    if page:
                        page.update()
                return _on_change
            itens_column.controls.append(
                ft.Container(
                    padding=10,
                    border_radius=8,
                    bgcolor=_color("card", dark),
                    content=ft.Row(
                        [
                            ft.Checkbox(value=bool(item.get("concluido")), on_change=_mk_toggle(item["id"])),
                            ft.Column(
                                [
                                    ft.Text(f"{item.get('dia')} - {item.get('tema')}", weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                    ft.Text(f"{item.get('atividade')} ({item.get('duracao_min')} min)", size=12, color=_color("texto_sec", dark)),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                        ],
                        spacing=10,
                    ),
                )
            )

    async def _gerar_plano_async():
        if not db or not user.get("id") or not page:
            return
        objetivo = (objetivo_field.value or "").strip() or "Aprovacao"
        data_prova = (data_prova_field.value or "").strip() or "-"
        limite_dias = 7
        if data_prova != "-":
            limite_inferido = _plan_day_limit(data_prova)
            if limite_inferido is None:
                _set_feedback_text(status_text, "Data invalida. Use DD/MM/AAAA.", "warning")
                page.update()
                return
            if limite_inferido <= 0:
                _set_feedback_text(status_text, "A data da prova ja passou. Informe uma data futura.", "warning")
                page.update()
                return
            limite_dias = limite_inferido
        try:
            tempo_diario = max(30, min(360, int((tempo_diario_field.value or "90").strip())))
        except ValueError:
            tempo_diario = 90
        loading.visible = True
        status_text.value = "Gerando plano semanal..."
        page.update()
        topicos = [r.get("tema", "Geral") for r in db.topicos_revisao(user["id"], limite=5)] or ["Geral"]
        service = _create_user_ai_service(user)
        itens = []
        try:
            if service:
                itens = await asyncio.to_thread(service.generate_study_plan, objetivo, data_prova, tempo_diario, topicos)
            if not itens:
                itens = [
                    {
                        "dia": d,
                        "tema": topicos[i % len(topicos)],
                        "atividade": "Questoes + revisao de erros + flashcards",
                        "duracao_min": tempo_diario,
                        "prioridade": 1 if i < 3 else 2,
                    }
                    for i, d in enumerate(dias_semana[:limite_dias])
                ]
            itens = _normalize_plan_items(itens, topicos, tempo_diario, limite_dias)
            db.salvar_plano_semanal(user["id"], objetivo, data_prova, tempo_diario, itens)
            if limite_dias < 7:
                status_text.value = f"Plano ajustado ao prazo real: {limite_dias} dia(s) ate a prova."
            else:
                status_text.value = "Plano semanal criado."
            _render_plan()
        except Exception as ex:
            log_exception(ex, "main._build_study_plan_body._gerar_plano_async")
            status_text.value = "Falha ao gerar plano."
        finally:
            loading.visible = False
            page.update()

    def _gerar_plano_click(_):
        if page:
            page.run_task(_gerar_plano_async)

    _render_plan()
    return ft.Container(
        expand=True,
        bgcolor=_color("fundo", dark),
        padding=20,
        content=ft.Column(
            [
                ft.Text("Plano Semanal", size=28, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                ft.Text("Gere um plano adaptativo e marque o progresso diario.", size=14, color=_color("texto_sec", dark)),
                ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=12,
                        content=ft.Column(
                            [
                                ft.Text("Configuracao do plano", size=16, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                ft.ResponsiveRow(
                                    [
                                        ft.Container(content=objetivo_field, col={"xs": 12, "md": 6}),
                                        ft.Container(content=data_prova_field, col={"xs": 6, "md": 3}),
                                        ft.Container(content=tempo_diario_field, col={"xs": 6, "md": 3}),
                                    ],
                                    spacing=12,
                                    run_spacing=8,
                                ),
                                ft.ResponsiveRow(
                                    [
                                        ft.Container(
                                            col={"xs": 12, "md": 3},
                                            content=ft.ElevatedButton("Gerar plano", icon=ft.Icons.AUTO_AWESOME, on_click=_gerar_plano_click, expand=True),
                                        ),
                                        ft.Container(
                                            col={"xs": 12, "md": 6},
                                            content=ft.Row([loading, ft.Container(content=status_text, expand=True)], spacing=10, wrap=True),
                                        ),
                                        ft.Container(
                                            col={"xs": 12, "md": 3},
                                            content=ft.ElevatedButton(
                                                "Estudar agora",
                                                icon=ft.Icons.PLAY_ARROW,
                                                on_click=lambda _: _start_prioritized_session(state, navigate),
                                                expand=True,
                                            ),
                                        ),
                                    ],
                                    run_spacing=6,
                                    spacing=8 if very_compact else 10,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                            ],
                            spacing=8,
                        ),
                    ),
                ),
                ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=12,
                        content=ft.Column(
                            [
                                ft.Text("Itens do plano", size=16, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                itens_column,
                            ],
                            spacing=8,
                        ),
                    ),
                ),
                ft.ElevatedButton("Voltar ao Inicio", on_click=lambda _: navigate("/home")),
            ],
            spacing=12,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        ),
    )


def _build_stats_body(state, navigate, dark: bool):
    user = state.get("usuario") or {}
    db = state.get("db")
    xp = user.get("xp", 0)
    nivel = user.get("nivel", "Bronze")
    acertos = user.get("acertos", 0)
    total = user.get("total_questoes", 0)
    taxa = (acertos / total * 100) if total else 0
    progresso_diario = {
        "meta_questoes": int(user.get("meta_questoes_diaria") or 20),
        "questoes_respondidas": 0,
        "streak_dias": int(user.get("streak_dias") or 0),
        "flashcards_revisados": 0,
        "discursivas_corrigidas": 0,
    }
    if db and user.get("id"):
        try:
            progresso_diario = db.obter_progresso_diario(user["id"])
        except Exception as ex:
            log_exception(ex, "main._build_stats_body.obter_progresso_diario")
    recado = "Constancia > perfeicao: mantenha o ritmo diario."
    if taxa >= 75:
        recado = "Excelente precisao. Vale subir dificuldade em parte das sessoes."
    elif taxa >= 50:
        recado = "Bom caminho. Priorize revisao dos erros para ganhar consistencia."

    resumo_cards = ft.ResponsiveRow(
        controls=[
            ft.Container(
                col={"sm": 6, "md": 3},
                content=ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=12,
                        content=ft.Column(
                            [ft.Text("XP Total", size=12, color=_color("texto_sec", dark)), ft.Text(str(xp), size=22, weight=ft.FontWeight.BOLD)],
                            spacing=4,
                        ),
                    ),
                ),
            ),
            ft.Container(
                col={"sm": 6, "md": 3},
                content=ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=12,
                        content=ft.Column(
                            [ft.Text("Nivel", size=12, color=_color("texto_sec", dark)), ft.Text(str(nivel), size=22, weight=ft.FontWeight.BOLD)],
                            spacing=4,
                        ),
                    ),
                ),
            ),
            ft.Container(
                col={"sm": 6, "md": 3},
                content=ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=12,
                        content=ft.Column(
                            [ft.Text("Taxa de acerto", size=12, color=_color("texto_sec", dark)), ft.Text(f"{taxa:.1f}%", size=22, weight=ft.FontWeight.BOLD)],
                            spacing=4,
                        ),
                    ),
                ),
            ),
            ft.Container(
                col={"sm": 6, "md": 3},
                content=ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=12,
                        content=ft.Column(
                            [
                                ft.Text("Meta diaria", size=12, color=_color("texto_sec", dark)),
                                ft.Text(
                                    f"{int(progresso_diario.get('questoes_respondidas', 0))}/{int(progresso_diario.get('meta_questoes', 20))}",
                                    size=22,
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ],
                            spacing=4,
                        ),
                    ),
                ),
            ),
        ],
        spacing=8,
        run_spacing=8,
    )

    atividade_card = ft.Card(
        elevation=1,
        content=ft.Container(
            padding=12,
            content=ft.Column(
                [
                    ft.Text("Atividade de hoje", size=16, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                    ft.Row(
                        [
                            ft.Container(
                                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                                border_radius=999,
                                bgcolor=ft.Colors.with_opacity(0.10, CORES["primaria"]),
                                content=ft.Text(
                                    f"{int(progresso_diario.get('flashcards_revisados', 0))} flashcards",
                                    color=CORES["primaria"],
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ),
                            ft.Container(
                                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                                border_radius=999,
                                bgcolor=ft.Colors.with_opacity(0.10, CORES["acento"]),
                                content=ft.Text(
                                    f"{int(progresso_diario.get('discursivas_corrigidas', 0))} discursivas",
                                    color=CORES["acento"],
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ),
                            ft.Container(
                                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                                border_radius=999,
                                bgcolor=ft.Colors.with_opacity(0.10, CORES["warning"]),
                                content=ft.Text(
                                    f"Streak {int(progresso_diario.get('streak_dias', 0))} dia(s)",
                                    color=CORES["warning"],
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ),
                        ],
                        wrap=True,
                        spacing=8,
                    ),
                    ft.Text(recado, size=12, color=_color("texto_sec", dark)),
                ],
                spacing=10,
            ),
        ),
    )

    return ft.Container(
        expand=True,
        bgcolor=_color("fundo", dark),
        padding=20,
        content=ft.Column(
            [
                ft.Text("Estatisticas", size=28, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                ft.Text("Resumo rapido do desempenho.", size=14, color=_color("texto_sec", dark)),
                resumo_cards,
                atividade_card,
                ft.ElevatedButton("Voltar ao Inicio", on_click=lambda _: navigate("/home")),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        ),
    )


def _build_profile_body(state, navigate, dark: bool):
    user = state.get("usuario") or {}
    db = state.get("db")
    page = state.get("page")
    xp = int(user.get("xp", 0) or 0)
    nivel = str(user.get("nivel", "Bronze") or "Bronze")
    acertos = int(user.get("acertos", 0) or 0)
    total = int(user.get("total_questoes", 0) or 0)
    taxa = (acertos / total * 100.0) if total > 0 else 0.0
    streak = int(user.get("streak_dias", 0) or 0)
    economia = "Ativo" if bool(user.get("economia_mode")) else "Inativo"
    tema = "Escuro" if state.get("tema_escuro") else "Claro"
    nome = str(user.get("nome", "") or "")
    identificador = str(user.get("email", "") or "")
    id_edit_field = ft.TextField(
        label="ID de acesso",
        value=identificador,
        hint_text="Digite um novo ID",
        expand=True,
    )
    id_feedback = ft.Text("", size=12, color=_color("texto_sec", dark), visible=False)

    def _salvar_id(_):
        if not db or not user.get("id"):
            return
        novo_id = (id_edit_field.value or "").strip().lower()
        if novo_id == (identificador or "").strip().lower():
            id_feedback.value = "Nenhuma alteracao no ID."
            id_feedback.color = _color("texto_sec", dark)
            id_feedback.visible = True
            if page:
                page.update()
            return
        ok, msg = db.atualizar_identificador(user["id"], novo_id)
        id_feedback.value = msg
        id_feedback.color = CORES["sucesso"] if ok else CORES["erro"]
        id_feedback.visible = True
        if ok:
            state["usuario"]["email"] = novo_id
            user["email"] = novo_id
        if page:
            page.update()

    resumo_cards = ft.ResponsiveRow(
        controls=[
            ft.Container(
                col={"sm": 6, "md": 3},
                content=ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=12,
                        content=ft.Column(
                            [
                                ft.Text("Nivel", size=12, color=_color("texto_sec", dark)),
                                ft.Text(nivel, size=18, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                            ],
                            spacing=4,
                        ),
                    ),
                ),
            ),
            ft.Container(
                col={"sm": 6, "md": 3},
                content=ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=12,
                        content=ft.Column(
                            [
                                ft.Text("XP", size=12, color=_color("texto_sec", dark)),
                                ft.Text(str(xp), size=18, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                            ],
                            spacing=4,
                        ),
                    ),
                ),
            ),
            ft.Container(
                col={"sm": 6, "md": 3},
                content=ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=12,
                        content=ft.Column(
                            [
                                ft.Text("Taxa de acerto", size=12, color=_color("texto_sec", dark)),
                                ft.Text(f"{taxa:.1f}%", size=18, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                            ],
                            spacing=4,
                        ),
                    ),
                ),
            ),
            ft.Container(
                col={"sm": 6, "md": 3},
                content=ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=12,
                        content=ft.Column(
                            [
                                ft.Text("Streak", size=12, color=_color("texto_sec", dark)),
                                ft.Text(f"{streak} dia(s)", size=18, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                            ],
                            spacing=4,
                        ),
                    ),
                ),
            ),
        ],
        spacing=8,
        run_spacing=8,
    )

    return ft.Container(
        expand=True,
        bgcolor=_color("fundo", dark),
        padding=20,
        content=ft.Column(
            [
                ft.Text("Perfil", size=28, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                ft.Text("Resumo da sua conta e preferencias.", size=14, color=_color("texto_sec", dark)),
                resumo_cards,
                ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=12,
                        content=ft.Column(
                            [
                                ft.Text("Conta", size=16, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                ft.ListTile(
                                    leading=ft.Icon(ft.Icons.PERSON),
                                    title=ft.Text("Nome"),
                                    subtitle=ft.Text(nome or "-"),
                                ),
                                ft.ResponsiveRow(
                                    [
                                        ft.Container(
                                            col={"xs": 12, "md": 9},
                                            content=ft.Row(
                                                [
                                                    ft.Icon(ft.Icons.BADGE, color=_color("texto_sec", dark)),
                                                    ft.Container(expand=True, content=id_edit_field),
                                                ],
                                                spacing=10,
                                                vertical_alignment=ft.CrossAxisAlignment.END,
                                            ),
                                        ),
                                        ft.Container(
                                            col={"xs": 12, "md": 3},
                                            content=ft.ElevatedButton(
                                                "Salvar ID",
                                                icon=ft.Icons.SAVE,
                                                on_click=_salvar_id,
                                                expand=True,
                                            ),
                                        ),
                                    ],
                                    run_spacing=6,
                                    spacing=10,
                                    vertical_alignment=ft.CrossAxisAlignment.END,
                                ),
                                id_feedback,
                            ],
                            spacing=4,
                        ),
                    ),
                ),
                ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=12,
                        content=ft.Column(
                            [
                                ft.Text("Estudo e preferencias", size=16, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                ft.ListTile(
                                    leading=ft.Icon(ft.Icons.SAVINGS),
                                    title=ft.Text("Modo economia IA"),
                                    trailing=ft.Text(economia, color=_color("texto_sec", dark)),
                                ),
                                ft.ListTile(
                                    leading=ft.Icon(ft.Icons.DARK_MODE),
                                    title=ft.Text("Tema"),
                                    trailing=ft.Text(tema, color=_color("texto_sec", dark)),
                                ),
                            ],
                            spacing=4,
                        ),
                    ),
                ),
                ft.ElevatedButton("Voltar ao Inicio", on_click=lambda _: navigate("/home")),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        ),
    )


def _build_ranking_body(state, navigate, dark: bool):
    db = state["db"]
    user = state.get("usuario") or {}
    ranking = db.obter_ranking()
    total_participantes = len(ranking)
    top_xp = int((ranking[0]["xp"] if ranking else 0) or 0)
    meu_nome = str(user.get("nome", "") or "").strip().lower()
    minha_posicao = next(
        (idx for idx, r in enumerate(ranking, 1) if str(r.get("nome", "")).strip().lower() == meu_nome),
        None,
    )

    resumo = ft.ResponsiveRow(
        controls=[
            ft.Container(
                col={"sm": 6, "md": 3},
                content=ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=12,
                        content=ft.Column(
                            [
                                ft.Text("Participantes", size=12, color=_color("texto_sec", dark)),
                                ft.Text(str(total_participantes), size=18, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                            ],
                            spacing=4,
                        ),
                    ),
                ),
            ),
            ft.Container(
                col={"sm": 6, "md": 3},
                content=ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=12,
                        content=ft.Column(
                            [
                                ft.Text("Top XP", size=12, color=_color("texto_sec", dark)),
                                ft.Text(str(top_xp), size=18, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                            ],
                            spacing=4,
                        ),
                    ),
                ),
            ),
            ft.Container(
                col={"sm": 12, "md": 6},
                content=ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=12,
                        content=ft.Column(
                            [
                                ft.Text("Sua posicao", size=12, color=_color("texto_sec", dark)),
                                ft.Text(
                                    f"#{minha_posicao}" if minha_posicao else "Fora do ranking",
                                    size=18,
                                    weight=ft.FontWeight.BOLD,
                                    color=CORES["primaria"] if minha_posicao else _color("texto_sec", dark),
                                ),
                            ],
                            spacing=4,
                        ),
                    ),
                ),
            ),
        ],
        spacing=8,
        run_spacing=8,
    )

    medalhas = {1: ("1", CORES["ouro"]), 2: ("2", CORES["prata"]), 3: ("3", CORES["bronze"])}
    ranking_rows = []
    for idx, r in enumerate(ranking, 1):
        medalha_texto, medalha_cor = medalhas.get(idx, (str(idx), _color("texto_sec", dark)))
        destaque_me = str(r.get("nome", "")).strip().lower() == meu_nome
        ranking_rows.append(
            ft.Container(
                padding=12,
                border_radius=12,
                bgcolor=ft.Colors.with_opacity(0.06, CORES["primaria"]) if destaque_me else _color("card", dark),
                border=ft.border.all(
                    1,
                    ft.Colors.with_opacity(0.20, CORES["primaria"]) if destaque_me else _soft_border(dark, 0.08),
                ),
                content=ft.Row(
                    [
                        ft.Container(
                            width=32,
                            height=32,
                            alignment=ft.Alignment(0, 0),
                            border_radius=999,
                            bgcolor=ft.Colors.with_opacity(0.14, medalha_cor),
                            content=ft.Text(medalha_texto, color=medalha_cor, weight=ft.FontWeight.BOLD),
                        ),
                        ft.Column(
                            [
                                ft.Text(
                                    r.get("nome", ""),
                                    size=15,
                                    weight=ft.FontWeight.BOLD if destaque_me else ft.FontWeight.W_600,
                                    color=_color("texto", dark),
                                ),
                                ft.Text(
                                    f"Taxa {float(r.get('taxa_acerto', 0) or 0):.1f}%",
                                    size=12,
                                    color=_color("texto_sec", dark),
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Container(
                            padding=ft.padding.symmetric(horizontal=10, vertical=6),
                            border_radius=999,
                            bgcolor=ft.Colors.with_opacity(0.10, CORES["primaria"]),
                            content=ft.Text(
                                f"{int(r.get('xp', 0) or 0)} XP",
                                color=CORES["primaria"],
                                weight=ft.FontWeight.BOLD,
                            ),
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
        )
    if not ranking_rows:
        ranking_rows.append(ft.Text("Sem dados ainda.", color=_color("texto_sec", dark)))

    return ft.Container(
        expand=True,
        bgcolor=_color("fundo", dark),
        padding=20,
        content=ft.Column(
            [
                ft.Text("Ranking", size=28, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                ft.Text("Competicao por XP com destaque para seu progresso.", size=14, color=_color("texto_sec", dark)),
                resumo,
                ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=10,
                        content=ft.Column(ranking_rows, spacing=8),
                    ),
                ),
                ft.Container(height=12),
                ft.ElevatedButton("Voltar ao Inicio", on_click=lambda _: navigate("/home")),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        ),
    )


def _build_conquistas_body(state, navigate, dark: bool):
    from config import CONQUISTAS
    total_conquistas = len(CONQUISTAS)
    total_xp = int(sum(int(c.get("xp_bonus", 0) or 0) for c in CONQUISTAS))
    rows = []
    for c in CONQUISTAS:
        rows.append(
            ft.Container(
                padding=12,
                border_radius=12,
                bgcolor=_color("card", dark),
                border=ft.border.all(1, _soft_border(dark, 0.08)),
                content=ft.Row(
                    [
                        ft.Container(
                            width=34,
                            height=34,
                            border_radius=999,
                            alignment=ft.Alignment(0, 0),
                            bgcolor=ft.Colors.with_opacity(0.10, CORES["primaria"]),
                            content=ft.Icon(ft.Icons.MILITARY_TECH, color=CORES["primaria"], size=18),
                        ),
                        ft.Column(
                            [
                                ft.Text(c["titulo"], weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                ft.Text(c["descricao"], size=12, color=_color("texto_sec", dark)),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Container(
                            padding=ft.padding.symmetric(horizontal=10, vertical=6),
                            border_radius=999,
                            bgcolor=ft.Colors.with_opacity(0.10, CORES["acento"]),
                            content=ft.Text(f"+{c['xp_bonus']} XP", color=CORES["acento"], weight=ft.FontWeight.BOLD),
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
        )
    return ft.Container(
        expand=True,
        bgcolor=_color("fundo", dark),
        padding=20,
        content=ft.Column(
            [
                ft.Text("Conquistas", size=28, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                ft.Text("Lista de medalhas disponiveis.", size=14, color=_color("texto_sec", dark)),
                ft.ResponsiveRow(
                    controls=[
                        ft.Container(
                            col={"sm": 6, "md": 4},
                            content=ft.Card(
                                elevation=1,
                                content=ft.Container(
                                    padding=12,
                                    content=ft.Column(
                                        [
                                            ft.Text("Total de conquistas", size=12, color=_color("texto_sec", dark)),
                                            ft.Text(str(total_conquistas), size=20, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                        ],
                                        spacing=4,
                                    ),
                                ),
                            ),
                        ),
                        ft.Container(
                            col={"sm": 6, "md": 4},
                            content=ft.Card(
                                elevation=1,
                                content=ft.Container(
                                    padding=12,
                                    content=ft.Column(
                                        [
                                            ft.Text("XP disponivel", size=12, color=_color("texto_sec", dark)),
                                            ft.Text(f"{total_xp}", size=20, weight=ft.FontWeight.BOLD, color=CORES["acento"]),
                                        ],
                                        spacing=4,
                                    ),
                                ),
                            ),
                        ),
                    ],
                    spacing=8,
                    run_spacing=8,
                ),
                ft.Card(content=ft.Container(padding=10, content=ft.Column(rows, spacing=8)), elevation=1),
                ft.ElevatedButton("Voltar ao Inicio", on_click=lambda _: navigate("/home")),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        ),
    )


def _build_plans_body(state, navigate, dark: bool):
    user = state.get("usuario") or {}
    db = state.get("db")
    backend = state.get("backend")
    page = state.get("page")
    if not db or not user.get("id"):
        return _build_placeholder_body("Planos", "E necessario login para gerenciar assinatura.", navigate, dark)

    # Render inicial instantaneo com cache local; sincronizacao online ocorre em background.
    sub = db.get_subscription_status(user["id"])
    plan_code = str(sub.get("plan_code") or "free")
    premium_active = bool(sub.get("premium_active"))
    premium_until = sub.get("premium_until")
    trial_used = int(sub.get("trial_used") or 0)

    status_text = ft.Text("", size=12, color=_color("texto_sec", dark))
    plan_value_text = ft.Text("", size=20, weight=ft.FontWeight.BOLD, color=_color("texto", dark))
    validade_value_text = ft.Text("", size=16, weight=ft.FontWeight.W_600, color=_color("texto", dark))
    operation_ring = ft.ProgressRing(width=16, height=16, stroke_width=2, visible=False)
    op_busy = {"value": False}
    checkout_state = {
        "checkout_id": "",
        "auth_token": "",
        "payment_code": "",
        "amount_cents": 0,
        "currency": "BRL",
        "plan_code": "",
        "provider": "",
        "checkout_url": "",
    }
    tx_id_field = ft.TextField(
        label="ID da transacao",
        hint_text="Cole o identificador do pagamento",
        width=280,
        visible=False,
    )
    payment_code_field = ft.TextField(label="Codigo de pagamento", read_only=True, width=280, visible=False)
    confirm_payment_button = ft.ElevatedButton("Confirmar pagamento", icon=ft.Icons.VERIFIED, visible=False)
    open_checkout_button = ft.ElevatedButton("Abrir pagamento", icon=ft.Icons.OPEN_IN_NEW, visible=False)
    refresh_payment_button = ft.OutlinedButton("Ja paguei, verificar status", icon=ft.Icons.REFRESH, visible=False)
    cancel_checkout_button = ft.TextButton("Cancelar checkout", icon=ft.Icons.CLOSE, visible=False)
    subscribe_monthly_button = ft.ElevatedButton("Assinar Mensal", icon=ft.Icons.PAYMENT)
    checkout_info_text = ft.Text("", size=12, color=_color("texto_sec", dark), visible=False)
    PAID_PLAN_CODES = {"premium_30"}

    def _set_status(message: str, tone: str = "info"):
        tone_map = {
            "info": _color("texto_sec", dark),
            "success": CORES["sucesso"],
            "warning": CORES["warning"],
            "error": CORES["erro"],
        }
        status_text.value = str(message or "")
        status_text.color = tone_map.get(tone, tone_map["info"])

    def _set_busy(value: bool):
        busy = bool(value)
        op_busy["value"] = busy
        operation_ring.visible = busy
        subscribe_monthly_button.disabled = busy
        confirm_payment_button.disabled = busy
        open_checkout_button.disabled = busy
        refresh_payment_button.disabled = busy
        cancel_checkout_button.disabled = busy
        if page:
            page.update()

    def _is_paid_plan_active() -> bool:
        code = str(plan_code or "").strip().lower()
        return bool(premium_active and code in PAID_PLAN_CODES)

    def _refresh_labels():
        if str(plan_code or "").strip().lower() == "trial" and premium_active:
            plano_atual = "Trial"
        elif _is_paid_plan_active():
            plano_atual = "Premium"
        else:
            plano_atual = "Free (trial usado)" if trial_used else "Free"
        validade_fmt = _format_datetime_label(str(premium_until or "")) if premium_until and premium_active else ""
        if premium_active and str(plan_code or "").strip().lower() == "trial":
            validade = f"Cortesia ate {validade_fmt}" if validade_fmt else "Cortesia ativa"
        elif premium_active:
            validade = f"Ate {validade_fmt}" if validade_fmt else "Premium ativo"
        else:
            validade = "Sem premium ativo"
        plan_value_text.value = plano_atual
        validade_value_text.value = validade
        validade_value_text.color = CORES["primaria"] if premium_active else _color("texto", dark)

    def _apply_status(s: dict):
        state["usuario"].update(s)
        nonlocal plan_code, premium_active, premium_until, trial_used
        plan_code = str(s.get("plan_code") or "free")
        premium_active = bool(s.get("premium_active"))
        premium_until = s.get("premium_until")
        trial_used = int(s.get("trial_used") or 0)
        _refresh_labels()
        if page:
            page.update()

    async def _fetch_backend_status_async() -> Optional[dict]:
        if not (backend and backend.enabled()):
            return None
        try:
            backend_uid = _backend_user_id(user)
            if int(user.get("backend_user_id") or 0) <= 0:
                await asyncio.to_thread(backend.upsert_user, backend_uid, user.get("nome", ""), user.get("email", ""))
            b = await asyncio.to_thread(backend.get_plan, backend_uid)
            return {
                "plan_code": b.get("plan_code", "free"),
                "premium_active": 1 if b.get("premium_active") else 0,
                "premium_until": b.get("premium_until"),
                "trial_used": 1 if b.get("plan_code") == "trial" else int(user.get("trial_used", 0) or 0),
            }
        except Exception as ex:
            log_exception(ex, "main._build_plans_body._fetch_backend_status_async")
            return None

    async def _refresh_status_async():
        remote = await _fetch_backend_status_async()
        if remote is not None:
            try:
                await asyncio.to_thread(
                    db.sync_subscription_status,
                    int(user["id"]),
                    str(remote.get("plan_code") or "free"),
                    remote.get("premium_until"),
                    int(remote.get("trial_used") or 0),
                )
            except Exception as ex:
                log_exception(ex, "main._build_plans_body._refresh_status_async.persist")
            _apply_status(remote)
            return
        _apply_status(db.get_subscription_status(user["id"]))

    def _refresh_status(_=None):
        if not page:
            return
        page.run_task(_refresh_status_async)

    def _set_checkout_visibility(visible: bool):
        manual_confirm = bool(visible and not checkout_state.get("checkout_url"))
        tx_id_field.visible = manual_confirm
        payment_code_field.visible = bool(visible)
        confirm_payment_button.visible = manual_confirm
        open_checkout_button.visible = bool(visible and checkout_state.get("checkout_url"))
        refresh_payment_button.visible = bool(visible)
        cancel_checkout_button.visible = bool(visible)
        checkout_info_text.visible = bool(visible)

    def _show_checkout_popup():
        if not page:
            return
        url = str(checkout_state.get("checkout_url") or "").strip()
        if not url:
            return
        link_field = ft.TextField(label="Link de pagamento", value=url, read_only=True, multiline=True, min_lines=2, max_lines=3)
        msg = ft.Text(
            f"Finalize o pagamento de {checkout_state.get('currency', 'BRL')} "
            f"{(int(checkout_state.get('amount_cents') or 0) / 100):.2f} no Mercado Pago."
        )

        def _copy_link(_=None):
            try:
                page.set_clipboard(url)
                page.snack_bar = ft.SnackBar(content=ft.Text("Link copiado."), bgcolor=CORES["sucesso"], show_close_icon=True)
                page.snack_bar.open = True
                page.update()
            except Exception:
                pass

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Checkout Mensal"),
            content=ft.Column([msg, link_field], tight=True, spacing=8),
            actions=[
                ft.TextButton("Copiar link", on_click=_copy_link),
                ft.TextButton("Fechar", on_click=lambda _: _close_dialog_compat(page, dlg)),
                ft.ElevatedButton("Abrir pagamento", icon=ft.Icons.OPEN_IN_NEW, on_click=lambda _: (_launch_url_compat(page, url, "plans.checkout_popup"), _close_dialog_compat(page, dlg))),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        _show_dialog_compat(page, dlg)

    def _clear_checkout():
        checkout_state.update(
            {
                "checkout_id": "",
                "auth_token": "",
                "payment_code": "",
                "amount_cents": 0,
                "currency": "BRL",
                "plan_code": "",
                "provider": "",
                "checkout_url": "",
            }
        )
        tx_id_field.value = ""
        payment_code_field.value = ""
        checkout_info_text.value = ""
        _set_checkout_visibility(False)

    async def _start_checkout_async(plano: str):
        if op_busy["value"]:
            return
        if not (backend and backend.enabled()):
            _set_status("Compra premium exige backend online. Configure BACKEND_URL.", "error")
            if page:
                page.update()
            return
        _set_busy(True)
        try:
            resp = await asyncio.to_thread(
                backend.start_checkout,
                _backend_user_id(user),
                plano,
                "mercadopago",
                str(user.get("nome") or ""),
                str(user.get("email") or ""),
            )
            if not bool(resp.get("ok")):
                _set_status(str(resp.get("message") or "Falha ao iniciar checkout."), "error")
                if page:
                    page.update()
                return
            checkout_state["checkout_id"] = str(resp.get("checkout_id") or "")
            checkout_state["auth_token"] = str(resp.get("auth_token") or "")
            checkout_state["payment_code"] = str(resp.get("payment_code") or "")
            checkout_state["amount_cents"] = int(resp.get("amount_cents") or 0)
            checkout_state["currency"] = str(resp.get("currency") or "BRL")
            checkout_state["plan_code"] = str(resp.get("plan_code") or plano)
            checkout_state["provider"] = str(resp.get("provider") or "")
            checkout_state["checkout_url"] = str(resp.get("checkout_url") or "").strip()
            payment_code_field.value = checkout_state["payment_code"]
            if checkout_state["checkout_url"]:
                checkout_info_text.value = (
                    f"Checkout iniciado para {checkout_state['plan_code']}. "
                    f"Valor: {checkout_state['currency']} {checkout_state['amount_cents'] / 100:.2f}. "
                    "Abra o pagamento, conclua no Mercado Pago e depois toque em verificar status."
                )
            else:
                checkout_info_text.value = (
                    f"Checkout iniciado para {checkout_state['plan_code']}. "
                    f"Valor: {checkout_state['currency']} {checkout_state['amount_cents'] / 100:.2f}. "
                    "Apos pagar, informe o ID da transacao e confirme."
                )
            _set_checkout_visibility(True)
            _set_status("Checkout criado. Complete o pagamento para liberar premium.", "warning")
            if checkout_state["checkout_url"]:
                _show_checkout_popup()
                try:
                    _launch_url_compat(page, checkout_state["checkout_url"], "plans.start_checkout")
                except Exception:
                    pass
        except Exception as ex:
            log_exception(ex, "main._build_plans_body._start_checkout")
            _set_status(f"Falha ao iniciar checkout: {ex}", "error")
        finally:
            _set_busy(False)
        if page:
            page.update()

    async def _confirm_checkout_async(_=None):
        if op_busy["value"]:
            return
        checkout_id = str(checkout_state.get("checkout_id") or "")
        auth_token = str(checkout_state.get("auth_token") or "")
        tx_id = str(tx_id_field.value or "").strip()
        if not checkout_id or not auth_token:
            _set_status("Nenhum checkout pendente.", "error")
            if page:
                page.update()
            return
        if not tx_id:
            _set_status("Informe o ID da transacao para confirmar.", "error")
            if page:
                page.update()
            return
        if not (backend and backend.enabled()):
            _set_status("Backend offline. Nao e possivel confirmar pagamento.", "error")
            if page:
                page.update()
            return
        _set_busy(True)
        ok = False
        msg = "Falha ao confirmar pagamento."
        try:
            resp = await asyncio.to_thread(
                backend.confirm_checkout,
                _backend_user_id(user),
                checkout_id,
                auth_token,
                tx_id,
            )
            ok = bool(resp.get("ok"))
            msg = str(resp.get("message") or ("Pagamento confirmado." if ok else msg))
        except Exception as ex:
            log_exception(ex, "main._build_plans_body._confirm_checkout")
            ok = False
            msg = f"Falha ao confirmar pagamento: {ex}"
        _set_status(msg, "success" if ok else "error")
        if ok:
            await _refresh_status_async()
            _clear_checkout()
        _set_busy(False)
        if page:
            page.update()

    def _open_checkout(_=None):
        url = str(checkout_state.get("checkout_url") or "").strip()
        if not url:
            _set_status("Checkout sem link de pagamento.", "error")
            if page:
                page.update()
            return
        if page:
            _show_checkout_popup()
            try:
                _launch_url_compat(page, url, "plans.open_checkout")
            except Exception:
                pass

    async def _refresh_after_payment_async(_=None):
        if op_busy["value"]:
            return
        _set_busy(True)
        checkout_id = str(checkout_state.get("checkout_id") or "").strip()
        reconcile_msg = ""
        if checkout_id and backend and backend.enabled():
            try:
                # Evita travar a UI por muito tempo quando o provedor de pagamento estiver lento.
                rec = await asyncio.wait_for(
                    asyncio.to_thread(backend.reconcile_checkout, _backend_user_id(user), checkout_id),
                    timeout=5.5,
                )
                reconcile_msg = str(rec.get("message") or "").strip()
            except Exception as ex:
                log_exception(ex, "main._build_plans_body._refresh_after_payment.reconcile")
                reconcile_msg = str(ex or "").strip()
        await _refresh_status_async()
        if _is_paid_plan_active():
            _set_status(reconcile_msg or "Pagamento confirmado. Premium ativo.", "success")
            _clear_checkout()
        else:
            if str(plan_code or "").strip().lower() == "trial":
                _set_status(reconcile_msg or "Seu trial esta ativo, mas pagamento ainda nao foi confirmado.", "warning")
            else:
                _set_status(reconcile_msg or "Pagamento ainda nao confirmado. Aguarde alguns segundos e tente novamente.", "warning")
        _set_busy(False)
        if page:
            page.update()

    def _start_checkout(_=None):
        if page:
            page.run_task(_start_checkout_async, "premium_30")

    def _confirm_checkout(_=None):
        if page:
            page.run_task(_confirm_checkout_async)

    def _refresh_after_payment(_=None):
        if page:
            page.run_task(_refresh_after_payment_async)

    confirm_payment_button.on_click = _confirm_checkout
    open_checkout_button.on_click = _open_checkout
    refresh_payment_button.on_click = _refresh_after_payment
    cancel_checkout_button.on_click = lambda _=None: (_clear_checkout(), page.update() if page else None)
    subscribe_monthly_button.on_click = _start_checkout

    _refresh_labels()

    backend_status_text = "Online ativo" if (backend and backend.enabled()) else "Offline local"
    backend_status_color = CORES["acento"] if (backend and backend.enabled()) else _color("texto_sec", dark)

    result = ft.Container(
        expand=True,
        bgcolor=_color("fundo", dark),
        padding=20,
        content=ft.Column(
            [
                ft.Text("Planos", size=28, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                ft.Text("Gerencie seu acesso Free/Premium.", size=14, color=_color("texto_sec", dark)),
                ft.Text(f"Sincronizacao: {backend_status_text}", size=12, color=backend_status_color),
                ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=12,
                        content=ft.Column(
                            [
                                ft.Text("Fluxo de compra premium", size=16, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                payment_code_field,
                                tx_id_field,
                                checkout_info_text,
                                ft.Row([operation_ring], alignment=ft.MainAxisAlignment.START),
                                ft.Row(
                                    [open_checkout_button, refresh_payment_button, confirm_payment_button, cancel_checkout_button],
                                    wrap=True,
                                    spacing=8,
                                ),
                            ],
                            spacing=8,
                        ),
                    ),
                ),
                ft.ResponsiveRow(
                    controls=[
                        ft.Container(
                            col={"sm": 6, "md": 4},
                            content=ft.Card(
                                elevation=1,
                                content=ft.Container(
                                    padding=12,
                                    content=ft.Column(
                                        [
                                            ft.Text("Plano atual", size=12, color=_color("texto_sec", dark)),
                                            plan_value_text,
                                        ],
                                        spacing=4,
                                    ),
                                ),
                            ),
                        ),
                        ft.Container(
                            col={"sm": 6, "md": 8},
                            content=ft.Card(
                                elevation=1,
                                content=ft.Container(
                                    padding=12,
                                    content=ft.Column(
                                        [
                                            ft.Text("Validade", size=12, color=_color("texto_sec", dark)),
                                            validade_value_text,
                                        ],
                                        spacing=4,
                                    ),
                                ),
                            ),
                        ),
                    ],
                    spacing=8,
                    run_spacing=8,
                ),
                ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=12,
                        content=ft.Column(
                            [
                                ft.Text("Free", size=16, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                ft.Text("Questoes e flashcards ilimitados em modo economico/lento.", size=12, color=_color("texto_sec", dark)),
                                ft.Text("Biblioteca: upload de 1 arquivo por vez.", size=12, color=_color("texto_sec", dark)),
                                ft.Text("Dissertativa: 1 correcao por dia.", size=12, color=_color("texto_sec", dark)),
                            ],
                            spacing=4,
                        ),
                    ),
                ),
                ft.ResponsiveRow(
                    controls=[
                        ft.Container(
                            col={"sm": 12, "md": 12},
                            content=ft.Card(
                                elevation=1,
                                content=ft.Container(
                                    padding=12,
                                    content=ft.Column(
                                        [
                                            ft.Text("Mensal", size=16, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                            ft.Text("Mesmo recurso, melhor custo-beneficio.", size=12, color=_color("texto_sec", dark)),
                                            ft.Text("Biblioteca: upload ilimitado por envio.", size=12, color=_color("texto_sec", dark)),
                                            subscribe_monthly_button,
                                        ],
                                        spacing=8,
                                    ),
                                ),
                            ),
                        ),
                    ],
                    spacing=8,
                    run_spacing=8,
                ),
                status_text,
                ft.ElevatedButton("Voltar ao Inicio", on_click=lambda _: navigate("/home")),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        ),
    )
    # Sincronizacao online em background para nao travar a abertura da tela.
    if backend and backend.enabled() and page:
        try:
            page.run_task(_refresh_status_async)
        except Exception:
            pass
    return result




def _build_settings_body(state, navigate, dark: bool):
    user = state.get("usuario") or {}
    db = state["db"]
    page = state.get("page")
    screen_w = _screen_width(page) if page else 1280
    compact = screen_w < 1000
    very_compact = screen_w < 760
    form_width = min(520, max(230, int(screen_w - (84 if very_compact else 120))))
    user_id = user.get("id")
    if not user_id:
        return _build_placeholder_body(
            "Configuracoes",
            "E necessario estar logado para alterar as configuracoes.",
            navigate,
            dark,
        )

    def _normalize_provider(value: str) -> str:
        v = str(value or "").strip().lower()
        if v in AI_PROVIDERS:
            return v
        for key, cfg in AI_PROVIDERS.items():
            if v == str(cfg.get("name", "")).strip().lower():
                return key
        return "gemini"

    current_provider = _normalize_provider(user.get("provider") or "gemini")
    provider_dropdown = ft.Dropdown(
        label="Provider IA",
        options=[ft.dropdown.Option(k, text=v["name"]) for k, v in AI_PROVIDERS.items()],
        value=current_provider,
        width=form_width if compact else 260,
    )

    model_dropdown_ref = {"control": None}

    def _build_model_dropdown(provider_key: str, selected_model: str = None):
        modelos = list(AI_PROVIDERS.get(provider_key, AI_PROVIDERS["gemini"]).get("models") or [])
        if not modelos:
            modelos = [AI_PROVIDERS["gemini"]["default_model"]]
        default_model = AI_PROVIDERS.get(provider_key, AI_PROVIDERS["gemini"]).get("default_model") or modelos[0]
        chosen = selected_model if selected_model in modelos else default_model
        dd = ft.Dropdown(
            label="Modelo padrao",
            options=[ft.dropdown.Option(m) for m in modelos],
            value=chosen,
            width=form_width if compact else 360,
        )
        model_dropdown_ref["control"] = dd
        return dd

    model_dropdown_slot = ft.Container(
        content=_build_model_dropdown(
            current_provider,
            user.get("model") or AI_PROVIDERS[current_provider]["default_model"],
        )
    )

    api_key_field = ft.TextField(
        label="API key",
        hint_text="sk-... ou gs://...",
        width=form_width if compact else 520,
        password=True,
        can_reveal_password=True,
        value=user.get("api_key") or "",
    )
    economia_mode_switch = ft.Switch(
        value=bool(user.get("economia_mode")),
    )
    telemetry_opt_in_switch = ft.Switch(
        value=bool(user.get("telemetry_opt_in")),
    )
    save_feedback = ft.Text("", size=12, color=_color("texto_sec", dark), visible=False)

    def _open_external_link(url: str):
        if not page:
            return
        try:
            _launch_url_compat(page, url, "settings_open_external_link")
        except Exception as ex:
            log_exception(ex, "settings_open_external_link")

    economia_row = ft.Row(
        [
            economia_mode_switch,
            ft.Container(
                expand=True,
                content=ft.Text(
                    "Modo economia (prioriza modelos mais baratos/estaveis)",
                    size=12 if very_compact else 13,
                    color=_color("texto", dark),
                ),
            ),
        ],
        spacing=8,
        wrap=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    telemetry_row = ft.Row(
        [
            telemetry_opt_in_switch,
            ft.Container(
                expand=True,
                content=ft.Text(
                    "Telemetria anonima (opt-in para melhorias do produto)",
                    size=12 if very_compact else 13,
                    color=_color("texto", dark),
                ),
            ),
        ],
        spacing=8,
        wrap=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    def _on_provider_change(e):
        selecionado = _normalize_provider(getattr(e.control, "value", None))
        provider_dropdown.value = selecionado
        modelo_atual = (model_dropdown_ref.get("control").value if model_dropdown_ref.get("control") else None)
        model_dropdown_slot.content = _build_model_dropdown(selecionado, modelo_atual)
        model_dropdown_slot.update()

    # Flet 0.80.x usa on_select no Dropdown (on_change nao existe).
    provider_dropdown.on_select = _on_provider_change
    if hasattr(provider_dropdown, "on_change"):
        provider_dropdown.on_change = _on_provider_change

    def save(e):
        try:
            provider_value = _normalize_provider(provider_dropdown.value)
            modelos_validos = AI_PROVIDERS.get(provider_value, AI_PROVIDERS["gemini"]).get("models") or []
            selected_model = model_dropdown_ref.get("control").value if model_dropdown_ref.get("control") else None
            model_value = selected_model if selected_model in modelos_validos else AI_PROVIDERS.get(provider_value, {}).get("default_model")
            api_value = (api_key_field.value or "").strip() or None
            db.atualizar_provider_ia(user_id, provider_value, model_value)
            db.atualizar_api_key(user_id, api_value)
            db.atualizar_economia_ia(user_id, bool(economia_mode_switch.value))
            db.atualizar_telemetria_opt_in(user_id, bool(telemetry_opt_in_switch.value))
            state["usuario"]["provider"] = provider_value
            state["usuario"]["model"] = model_value
            state["usuario"]["api_key"] = api_value
            state["usuario"]["economia_mode"] = 1 if economia_mode_switch.value else 0
            state["usuario"]["telemetry_opt_in"] = 1 if telemetry_opt_in_switch.value else 0

            backend_ref = state.get("backend")
            backend_uid = _backend_user_id(state.get("usuario") or {})

            async def _push_settings_remote_async():
                if not (backend_ref and backend_ref.enabled()):
                    return
                try:
                    await asyncio.to_thread(
                        backend_ref.upsert_user_settings,
                        int(backend_uid),
                        provider_value,
                        model_value,
                        api_value,
                        bool(economia_mode_switch.value),
                        bool(telemetry_opt_in_switch.value),
                    )
                except Exception as ex_sync:
                    log_exception(ex_sync, "settings_save.sync_remote")

            if page and backend_ref and backend_ref.enabled():
                try:
                    page.run_task(_push_settings_remote_async)
                except Exception as ex_task:
                    log_exception(ex_task, "settings_save.schedule_remote_sync")

            log_event("settings_save", f"user_id={user_id} provider={provider_value} model={model_value}")
            _set_feedback_text(save_feedback, "Configuracoes salvas com sucesso.", "success")
            save_feedback.visible = True
            if page:
                page.snack_bar = ft.SnackBar(
                    content=ft.Text("Configuracoes salvas"),
                    bgcolor=CORES["sucesso"],
                    show_close_icon=True,
                )
                page.snack_bar.open = True
                page.update()
        except Exception as ex:
            log_exception(ex, "settings_save")
            _set_feedback_text(save_feedback, "Erro ao salvar configuracoes.", "error")
            save_feedback.visible = True
            if page:
                page.snack_bar = ft.SnackBar(
                    content=ft.Text("Erro ao salvar configuracoes", color="white"),
                    bgcolor=CORES["erro"],
                    show_close_icon=True,
                )
                page.snack_bar.open = True
                page.update()

    retorno = ft.Container(
        expand=True,
        bgcolor=_color("fundo", dark),
        padding=20,
        content=ft.Column(
            [
                ft.Text("Configuracoes", size=28, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                ft.Text("Ajustes rapidos de IA.", size=14, color=_color("texto_sec", dark)),
                ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=12,
                        content=ft.Column(
                            [
                                ft.Text("IA e preferencia de uso", size=16, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                provider_dropdown,
                                model_dropdown_slot,
                                api_key_field,
                                ft.Row(
                                    [
                                        ft.TextButton(
                                            "Criar chave Gemini",
                                            icon=ft.Icons.OPEN_IN_NEW,
                                            on_click=lambda _: _open_external_link("https://aistudio.google.com/app/apikey"),
                                        ),
                                        ft.TextButton(
                                            "Criar chave OpenAI",
                                            icon=ft.Icons.OPEN_IN_NEW,
                                            on_click=lambda _: _open_external_link("https://platform.openai.com/api-keys"),
                                        ),
                                    ],
                                    wrap=True,
                                    spacing=6,
                                ),
                                economia_row,
                                telemetry_row,
                                ft.Text(
                                    "A chave e armazenada localmente e usada para gerar conteudo com IA.",
                                    size=12,
                                    color=_color("texto_sec", dark),
                                ),
                                ft.ElevatedButton("Salvar", icon=ft.Icons.SAVE, on_click=save),
                                save_feedback,
                            ],
                            spacing=10,
                        ),
                    ),
                ),
                ft.Container(height=12),
                ft.ElevatedButton("Voltar ao Inicio", on_click=lambda _: navigate("/home")),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        ),
    )
    return retorno


def _open_menu_dialog(page: ft.Page, state: dict, current_route: str, dark: bool, navigate, on_logout, toggle_dark):
    user = state.get("usuario") or {}
    selected_index = 0
    for idx, (route, _, _) in enumerate(APP_ROUTES):
        if route == current_route:
            selected_index = idx
            break

    def _close_drawer_safe():
        try:
            if hasattr(page, "close_drawer"):
                page.close_drawer()
                return
        except Exception:
            pass
        try:
            if getattr(page, "drawer", None):
                page.drawer.open = False
                page.update()
        except Exception:
            pass

    def _on_menu_change(e):
        idx = getattr(e.control, "selected_index", None)
        try:
            idx = int(idx)
        except Exception:
            return
        if idx < 0 or idx >= len(APP_ROUTES):
            return
        target_route = APP_ROUTES[idx][0]
        _close_drawer_safe()
        if target_route != current_route:
            navigate(target_route)

    def _logout_and_close(e):
        _close_drawer_safe()
        on_logout(e)

    destinations = [
        ft.NavigationDrawerDestination(
            icon=icon,
            selected_icon=ft.Icons.CHECK_CIRCLE,
            label=label,
        )
        for _, label, icon in APP_ROUTES
    ]

    drawer = ft.NavigationDrawer(
        selected_index=selected_index,
        on_change=_on_menu_change,
        bgcolor=_color("card", dark),
        controls=[
            ft.Container(
                padding=ft.padding.only(left=16, right=12, top=12, bottom=8),
                content=ft.Column(
                    [
                        ft.Text("Menu", size=20, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                        ft.Text(
                            f"{user.get('nome', '')} ({user.get('email', '')})" if user.get("email") else f"{user.get('nome', '')}",
                            size=12,
                            color=_color("texto_sec", dark),
                        ),
                    ],
                    spacing=4,
                ),
            ),
            ft.Divider(height=1, color=_soft_border(dark, 0.12)),
            *destinations,
            ft.Divider(height=1, color=_soft_border(dark, 0.12)),
            ft.Container(
                padding=ft.padding.symmetric(horizontal=12, vertical=8),
                content=ft.Row(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.DARK_MODE, size=16, color=_color("texto_sec", dark)),
                                ft.Text("Modo escuro", color=_color("texto", dark)),
                            ],
                            spacing=8,
                        ),
                        ft.Switch(value=dark, on_change=toggle_dark, scale=0.9),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ),
            ft.Container(
                padding=ft.padding.only(left=12, right=12, bottom=12),
                content=ft.ElevatedButton(
                    "Sair",
                    icon=ft.Icons.LOGOUT,
                    on_click=_logout_and_close,
                    bgcolor=CORES["erro"],
                    color="white",
                ),
            ),
        ],
    )

    _sanitize_control_texts(drawer)
    page.drawer = drawer
    if hasattr(page, "show_drawer"):
        page.show_drawer()
        try:
            page.update()
        except Exception:
            pass
        return
    try:
        drawer.open = True
        page.update()
    except Exception:
        pass


def _build_shell_view(page: ft.Page, state: dict, route: str, body: ft.Control, on_logout, dark: bool, toggle_dark):
    def navigate(target: str):
        target_route = _normalize_route_path(target)
        current_route = _normalize_route_path(page.route or route or "/home")
        if current_route not in {"/", "/login"} and current_route != target_route:
            history = state.setdefault("route_history", [])
            if not history or history[-1] != current_route:
                history.append(current_route)
            # Mantem historico enxuto para evitar crescimento indefinido.
            if len(history) > 80:
                del history[:-80]
        page.go(target_route)

    def go_back(_=None):
        try:
            current_route = _normalize_route_path(page.route or route or "/home")
            history = state.setdefault("route_history", [])
            while history:
                prev = _normalize_route_path(history.pop())
                if prev and prev not in {"/", "/login"} and prev != current_route:
                    page.go(prev)
                    return
            page.go("/home" if state.get("usuario") else "/login")
        except Exception:
            page.go("/home" if state.get("usuario") else "/login")

    menu_ref = {"panel": None, "scrim": None, "row": None}

    def _set_inline_menu_visible(visible: bool):
        panel = menu_ref.get("panel")
        scrim = menu_ref.get("scrim")
        row = menu_ref.get("row")
        is_open = bool(visible)
        if panel is not None:
            panel.visible = is_open
        if scrim is not None:
            scrim.visible = is_open
        if row is not None:
            row.visible = is_open
        state["menu_inline_open"] = is_open
        try:
            if panel is not None:
                panel.update()
            if scrim is not None:
                scrim.update()
            if row is not None:
                row.update()
        except Exception:
            page.update()

    def _close_inline_menu(_=None):
        panel = menu_ref["panel"]
        if panel is None:
            return
        if bool(panel.visible):
            _set_inline_menu_visible(False)

    def _toggle_inline_menu(_=None):
        panel = menu_ref["panel"]
        if panel is None:
            return
        is_open = not bool(panel.visible)
        _set_inline_menu_visible(is_open)
        log_event("menu_click", f"route={route} inline_open={panel.visible}")

    def _navigate_from_menu(target: str):
        _close_inline_menu()
        navigate(target)

    def _toggle_dark_icon(_=None):
        class _Ctl:
            value = not bool(dark)
        class _Evt:
            control = _Ctl()
        toggle_dark(_Evt())

    normalized_route = _normalize_route_path(route)
    screen_w = _screen_width(page)
    compact = screen_w < 980
    very_compact = screen_w < 760
    show_back = normalized_route not in {"/home", "/welcome"}
    route_labels = {r: label for r, label, _ in APP_ROUTES}
    route_labels.update({r: label for r, label, _ in APP_ROUTES_SECONDARY})
    route_labels.update(
        {
            "/welcome": "Boas-vindas",
            "/simulado": "Simulado",
            "/revisao/sessao": "Revisao do Dia",
            "/revisao/erros": "Caderno de Erros",
            "/revisao/marcadas": "Marcadas",
        }
    )
    route_label = route_labels.get(normalized_route)
    if not route_label:
        clean_route = normalized_route.strip("/") or "home"
        route_label = clean_route.replace("-", " ").replace("/", " / ").title()
    focus_routes = {"/quiz", "/flashcards", "/open-quiz"}
    focus_mode = normalized_route in focus_routes

    if normalized_route == "/home":
        title = "Quiz Vance"
    elif focus_mode and not very_compact:
        title = f"Modo foco: {route_label}"
    else:
        title = route_label

    user = state.get("usuario") or {}

    right_controls = []
    if very_compact:
        right_controls.append(
            ft.IconButton(
                icon=ft.Icons.DARK_MODE if dark else ft.Icons.LIGHT_MODE,
                tooltip="Tema",
                on_click=_toggle_dark_icon,
                icon_color=_color("texto_sec", dark),
            )
        )
    else:
        right_controls.append(
            ft.Row(
                [
                    ft.Icon(ft.Icons.DARK_MODE, size=16, color=_color("texto_sec", dark)),
                    ft.Switch(value=dark, on_change=toggle_dark, scale=0.88 if compact else 0.92),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

    if not very_compact:
        user_text = f"{user.get('nome', '')}" if compact else f"{user.get('nome', '')} ({user.get('email', '')})"
        right_controls.append(ft.Text(user_text, size=11 if compact else 12, color=_color("texto_sec", dark), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS))

    if compact:
        right_controls.append(
            ft.IconButton(icon=ft.Icons.LOGOUT, tooltip="Sair", on_click=on_logout, icon_color=CORES["erro"])
        )
    else:
        right_controls.append(
            ft.ElevatedButton("Sair", on_click=on_logout, bgcolor=CORES["erro"], color="white")
        )

    inline_menu_controls = [
        ft.Text("Menu", size=18, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
        ft.Divider(height=1, color=_soft_border(dark, 0.12)),
    ]
    for target_route, label, icon in APP_ROUTES:
        selected = target_route == normalized_route
        inline_menu_controls.append(
            ft.TextButton(
                on_click=lambda _, r=target_route: _navigate_from_menu(r),
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.with_opacity(0.10, CORES["primaria"]) if selected else "transparent",
                    shape=ft.RoundedRectangleBorder(radius=10),
                    padding=ft.Padding(10, 8, 10, 8),
                ),
                content=ft.Row(
                    [
                        ft.Icon(icon, size=18, color=CORES["primaria"] if selected else _color("texto_sec", dark)),
                        ft.Text(
                            label,
                            size=13,
                            weight=ft.FontWeight.BOLD if selected else ft.FontWeight.W_500,
                            color=CORES["primaria"] if selected else _color("texto", dark),
                        ),
                    ],
                    spacing=10,
                ),
            )
        )

    inline_menu = ft.Container(
        visible=bool(state.get("menu_inline_open", False)),
        width=220 if not compact else max(150, min(200, int(screen_w * 0.46))),
        bgcolor=_color("card", dark),
        border=ft.border.only(right=ft.BorderSide(1, _soft_border(dark, 0.10))),
        padding=10,
        content=ft.Column(
            inline_menu_controls,
            spacing=4,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        ),
    )
    menu_ref["panel"] = inline_menu

    topbar = ft.Container(
        padding=ft.padding.symmetric(horizontal=8 if very_compact else (10 if compact else 16), vertical=10),
        bgcolor=ft.Colors.with_opacity(0.05, _color("texto", dark)),
        border=ft.border.only(bottom=ft.BorderSide(1, _soft_border(dark, 0.10))),
        content=ft.Row(
            [
                ft.Container(
                    expand=True,
                    content=ft.Row(
                        [
                            ft.IconButton(icon=ft.Icons.MENU_ROUNDED, tooltip="Menu", on_click=_toggle_inline_menu),
                            ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="Voltar", on_click=go_back, visible=show_back),
                            ft.Text(
                                title,
                                size=14 if very_compact else (16 if compact else 18),
                                weight=ft.FontWeight.W_700,
                                color=_color("texto", dark),
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                        spacing=2,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ),
                ft.Row(
                    right_controls,
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    menu_scrim = ft.Container(
        visible=bool(state.get("menu_inline_open", False)),
        expand=True,
        bgcolor=ft.Colors.with_opacity(0.20, "#000000"),
        on_click=_close_inline_menu,
    )
    menu_row = ft.Row(
        [
            inline_menu,
            ft.Container(expand=True, on_click=_close_inline_menu),
        ],
        spacing=0,
        expand=True,
        visible=bool(state.get("menu_inline_open", False)),
    )
    menu_ref["scrim"] = menu_scrim
    menu_ref["row"] = menu_row

    content = ft.Container(
        expand=True,
        padding=10 if very_compact else (12 if compact else 18),
        bgcolor=_color("fundo", dark),
        content=(
            ft.Stack(
                [
                    ft.Container(expand=True, content=body),
                    menu_scrim,
                    menu_row,
                ],
                expand=True,
            )
            if compact
            else ft.Row(
                [
                    inline_menu,
                    ft.Container(expand=True, content=body),
                ],
                spacing=0,
                expand=True,
            )
        ),
    )

    return ft.View(route=route, controls=[topbar, content], bgcolor=_color("fundo", dark))

def _build_revisao_body(state: dict, navigate, dark: bool):
    db = state.get("db")
    user = state.get("usuario") or {}
    user_id = int(user.get("id") or 0)
    counters = {"flashcards_pendentes": 0, "questoes_pendentes": 0}
    if db and user_id:
        try:
            counters = db.contadores_revisao(user_id)
        except Exception as ex:
            log_exception(ex, "main._build_revisao_body.contadores")

    flashcards_pendentes = int(counters.get("flashcards_pendentes") or 0)
    questoes_pendentes = int(counters.get("questoes_pendentes") or 0)
    total_hoje = flashcards_pendentes + questoes_pendentes

    def _card(title: str, desc: str, value: int, route: str, color: str):
        return ds_card(
            dark=dark,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(title, size=DS.FS_BODY, weight=DS.FW_SEMI, color=DS.text_color(dark)),
                            ft.Container(expand=True),
                            ds_badge(str(value), color=color),
                        ],
                        spacing=DS.SP_8,
                    ),
                    ft.Text(desc, size=DS.FS_CAPTION, color=DS.text_sec_color(dark)),
                    ft.Row(
                        [ds_btn_primary("Abrir", on_click=lambda _: navigate(route), dark=dark)],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
                spacing=DS.SP_8,
            ),
        )

    return ft.Container(
        expand=True,
        padding=DS.SP_16,
        content=ft.Column(
            [
                ds_section_title("Revisao", dark=dark),
                ft.Text(
                    f"{total_hoje} itens pendentes para hoje" if total_hoje else "Nada pendente para hoje",
                    size=DS.FS_BODY_S,
                    color=DS.text_sec_color(dark),
                ),
                _card("Revisao do Dia", "Fila combinada 3 flashcards -> 2 questoes", total_hoje, "/revisao/sessao", DS.P_500),
                _card("Caderno de Erros", "Questoes em que voce errou e precisam reforco", questoes_pendentes, "/revisao/erros", DS.ERRO),
                _card("Marcadas", "Questoes marcadas manualmente para revisar", questoes_pendentes, "/revisao/marcadas", DS.WARNING),
                _card("Flashcards", "Revisao ativa com lembrei/rever/pular", flashcards_pendentes, "/flashcards", DS.SUCESSO),
            ],
            spacing=DS.SP_12,
            scroll=ft.ScrollMode.AUTO,
        ),
    )


def _build_simulado_body(state: dict, navigate, dark: bool):
    page = state.get("page")
    user = state.get("usuario") or {}
    db = state.get("db")
    premium = _is_premium_active(user)
    user_id = int(user.get("id") or 0)
    policy = MockExamService(db) if db else None
    usados_hoje = policy.daily_used(user_id) if (policy and user_id and not premium) else 0
    plan_hint_text = (
        "Premium ativo: sem limite diario e com mais opcoes de quantidade."
        if premium
        else MockExamService.plan_hint(False)
    )
    usage_hint_text = (
        "Sem limite diario no Premium."
        if premium
        else f"Simulados usados hoje: {usados_hoje}"
    )

    tempo_field = ft.TextField(label="Tempo total (min)", value="60", keyboard_type=ft.KeyboardType.NUMBER, border_radius=DS.R_MD)
    dificuldade_dd = ft.Dropdown(
        label="Dificuldade",
        value="intermediario",
        options=[
            ft.dropdown.Option("facil", "Facil"),
            ft.dropdown.Option("intermediario", "Intermediario"),
            ft.dropdown.Option("dificil", "Dificil"),
        ],
    )
    preset_counts = MockExamService.preset_counts(premium)
    qtd_dd = ft.Dropdown(
        label="Quantidade",
        value=str(preset_counts[1] if len(preset_counts) > 1 else preset_counts[0]),
        options=[ft.dropdown.Option(str(v), f"{v} questoes") for v in preset_counts] + [ft.dropdown.Option("custom", "Custom")],
    )
    qtd_custom = ft.TextField(label="Qtd custom (opcional)", keyboard_type=ft.KeyboardType.NUMBER, border_radius=DS.R_MD)
    disciplina_field = ft.TextField(label="Disciplina (opcional)", border_radius=DS.R_MD)
    assunto_field = ft.TextField(label="Assunto (opcional)", border_radius=DS.R_MD)

    def _iniciar(_):
        if policy and user_id:
            allowed, _used, _limit = policy.can_start_today(user_id, premium=premium)
            if not allowed:
                _show_upgrade_dialog(page, navigate, "Plano Free: limite diario de simulado atingido.")
                return

        try:
            tempo = max(5, int(str(tempo_field.value or "60").strip()))
        except Exception:
            tempo = 60

        count = 20
        custom_raw = str(qtd_custom.value or "").strip()
        if custom_raw.isdigit():
            count = int(custom_raw)
        else:
            try:
                count = int(str(qtd_dd.value or "20"))
            except Exception:
                count = 20
        count, _capped = MockExamService.normalize_question_count(count, premium)

        disciplina = str(disciplina_field.value or "").strip()
        assunto = str(assunto_field.value or "").strip()
        disciplinas = [disciplina] if disciplina else []
        assuntos = [assunto] if assunto else []
        topic = disciplina or assunto or "Geral"
        state["quiz_preset"] = {
            "topic": topic,
            "count": str(count),
            "difficulty": dificuldade_dd.value or "intermediario",
            "simulado_mode": True,
            "feedback_imediato": False,
            "simulado_tempo": tempo,
            "advanced_filters": {
                "disciplinas": disciplinas,
                "assuntos": assuntos,
            },
            "reason": f"Modo Simulado - {tempo}min - {count} questoes",
        }
        navigate("/quiz")

    return ft.Container(
        expand=True,
        padding=DS.SP_16,
        content=ft.Column(
            [
                ds_section_title("Modo Simulado", dark=dark),
                ft.Text(plan_hint_text, size=DS.FS_CAPTION, color=DS.SUCESSO if premium else DS.WARNING),
                ft.Text(
                    usage_hint_text,
                    size=DS.FS_CAPTION,
                    color=DS.text_sec_color(dark),
                ),
                ds_card(
                    dark=dark,
                    content=ft.Column(
                        [
                            ft.ResponsiveRow(
                                [
                                    ft.Container(col={"xs": 6, "md": 3}, content=qtd_dd),
                                    ft.Container(col={"xs": 6, "md": 3}, content=qtd_custom),
                                    ft.Container(col={"xs": 6, "md": 3}, content=tempo_field),
                                    ft.Container(col={"xs": 6, "md": 3}, content=dificuldade_dd),
                                    ft.Container(col={"xs": 12, "md": 6}, content=disciplina_field),
                                    ft.Container(col={"xs": 12, "md": 6}, content=assunto_field),
                                ],
                                run_spacing=DS.SP_8,
                                spacing=DS.SP_8,
                            ),
                            ft.ResponsiveRow(
                                [
                                    ft.Container(
                                        col={"xs": 12, "md": 6},
                                        content=ds_btn_primary("Iniciar Simulado", on_click=_iniciar, dark=dark, icon=ft.Icons.PLAY_ARROW_ROUNDED),
                                    ),
                                    ft.Container(
                                        col={"xs": 12, "md": 6},
                                        content=ds_btn_ghost("Voltar", on_click=lambda _: navigate("/quiz"), dark=dark),
                                    ),
                                ],
                                run_spacing=DS.SP_8,
                                spacing=DS.SP_8,
                            ),
                        ],
                        spacing=DS.SP_10,
                    ),
                ),
            ],
            spacing=DS.SP_12,
            scroll=ft.ScrollMode.AUTO,
        ),
    )


def _build_mais_body(state: dict, navigate, dark: bool, on_logout, toggle_dark):
    """Tela Mais: hub com perfil + grid de atalhos para rotas secundarias."""
    usuario = state.get("usuario") or {}
    page = state.get("page")
    nome  = usuario.get("nome", "Usuario")
    email = usuario.get("email", "")

    from config import get_level_info
    xp   = int(usuario.get("xp_total") or 0)
    nivel_info = get_level_info(xp)
    nivel_nome = nivel_info.get("nome", "Iniciante")
    nivel_cor  = nivel_info.get("cor", DS.A_500)
    nivel_next = nivel_info.get("proximo_xp", 1000)
    nivel_prog = min(1.0, xp / max(nivel_next, 1))

    # ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ Perfil header ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬
    perfil_header = ds_card(
        dark=dark,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Text(nome[0].upper() if nome else "U", size=DS.FS_H2,
                                            weight=DS.FW_BOLD, color=DS.WHITE),
                            bgcolor=DS.P_500,
                            border_radius=DS.R_PILL,
                            width=56, height=56,
                            alignment=ft.Alignment(0, 0),
                        ),
                        ft.Column(
                            [
                                ft.Text(nome, size=DS.FS_BODY, weight=DS.FW_SEMI, color=DS.text_color(dark)),
                                ft.Text(email, size=DS.FS_CAPTION, color=DS.text_sec_color(dark)),
                                ds_badge(nivel_nome, color=nivel_cor),
                            ],
                            spacing=DS.SP_4,
                            expand=True,
                        ),
                        ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip="Editar perfil",
                                      icon_color=DS.text_sec_color(dark), icon_size=20,
                                      on_click=lambda _: navigate("/profile")),
                    ],
                    spacing=DS.SP_16,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=DS.SP_8),
                ft.Row(
                    [
                        ft.Text(f"{xp} XP", size=DS.FS_CAPTION, color=DS.text_sec_color(dark)),
                        ft.Container(expand=True),
                        ft.Text(f"{nivel_next} XP", size=DS.FS_CAPTION, color=DS.text_sec_color(dark)),
                    ]
                ),
                ds_progress_bar(nivel_prog, dark=dark, color=nivel_cor),
            ],
            spacing=DS.SP_8,
        ),
    )

    # ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ Grid de atalhos ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬
    def _atalho(icon, label, rota, cor=DS.P_500):
        return ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Icon(icon, size=24, color=cor),
                        bgcolor=f"{cor}1A",
                        border_radius=DS.R_LG,
                        padding=DS.SP_16,
                    ),
                    ft.Text(label, size=DS.FS_CAPTION, color=DS.text_color(dark),
                            text_align=ft.TextAlign.CENTER, max_lines=2),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=DS.SP_8,
            ),
            on_click=lambda _, r=rota: navigate(r),
            border_radius=DS.R_LG,
            bgcolor=DS.card_color(dark),
            border=ft.border.all(1, DS.border_color(dark, 0.08)),
            padding=DS.SP_16,
            ink=True,
        )

    grid_items = [
        _atalho(ft.Icons.STYLE_OUTLINED,         "Flashcards",    "/flashcards",  DS.A_500),
        _atalho(ft.Icons.EDIT_NOTE_OUTLINED,      "Dissertativo",  "/open-quiz",   DS.INFO),
        _atalho(ft.Icons.LOCAL_LIBRARY_OUTLINED,  "Biblioteca",    "/library",     DS.P_500),
        _atalho(ft.Icons.INSIGHTS_OUTLINED,       "Estatisticas",  "/stats",       DS.WARNING),
        _atalho(ft.Icons.TIMER_OUTLINED,          "Simulado",      "/simulado",    DS.WARNING),
        _atalho(ft.Icons.EMOJI_EVENTS_OUTLINED,   "Ranking",       "/ranking",     DS.WARNING),
        _atalho(ft.Icons.MILITARY_TECH_OUTLINED,  "Conquistas",    "/conquistas",  DS.SUCESSO),
        _atalho(ft.Icons.STARS_OUTLINED,          "Planos",        "/plans",       DS.P_400),
        _atalho(ft.Icons.SETTINGS_OUTLINED,       "Configuracoes", "/settings",    DS.G_500),
    ]

    grid = ft.ResponsiveRow(
        controls=[
            ft.Container(col={"xs": 6, "sm": 4, "md": 3}, content=item)
            for item in grid_items
        ],
        run_spacing=DS.SP_12,
        spacing=DS.SP_12,
    )

    # ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ Conta e tema ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬
    conta_section = ds_card(
        dark=dark,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Row(
                            [ft.Icon(ft.Icons.DARK_MODE_OUTLINED, size=18, color=DS.text_sec_color(dark)),
                             ft.Text("Modo escuro", size=DS.FS_BODY_S, color=DS.text_color(dark))],
                            spacing=DS.SP_8,
                        ),
                        ft.Switch(value=dark, on_change=toggle_dark, active_color=DS.P_500, scale=0.9),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(height=1, color=DS.border_color(dark, 0.08)),
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.LOGOUT, size=18, color=DS.ERRO),
                            ft.Text("Sair", size=DS.FS_BODY_S, color=DS.ERRO, weight=DS.FW_MED),
                        ],
                        spacing=DS.SP_8,
                    ),
                    on_click=on_logout,
                    ink=True,
                    border_radius=DS.R_MD,
                    padding=ft.padding.symmetric(vertical=DS.SP_4),
                ),
            ],
            spacing=DS.SP_12,
        ),
    )

    support_email = str(os.getenv("QUIZVANCE_SUPPORT_EMAIL") or "suporte@quizvance.app").strip()
    terms_url = str(os.getenv("QUIZVANCE_TERMS_URL") or "").strip()
    privacy_url = str(os.getenv("QUIZVANCE_PRIVACY_URL") or "").strip()
    refund_url = str(os.getenv("QUIZVANCE_REFUND_URL") or "").strip()
    support_url = str(os.getenv("QUIZVANCE_SUPPORT_URL") or "").strip()

    def _open_external_or_warn(url: str, label: str):
        link = str(url or "").strip()
        if not link:
            if page:
                page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"{label} ainda nao configurado.", color="white"),
                    bgcolor=CORES["warning"],
                    show_close_icon=True,
                )
                page.snack_bar.open = True
                page.update()
            return
        _launch_url_compat(page, link, f"mais.open_{label.lower().replace(' ', '_')}")

    legal_section = ds_card(
        dark=dark,
        content=ft.Column(
            [
                ft.Text("Termos e suporte", size=DS.FS_BODY, weight=DS.FW_SEMI, color=DS.text_color(dark)),
                ft.Text(
                    "Para publicacao comercial, mantenha os links oficiais atualizados.",
                    size=DS.FS_CAPTION,
                    color=DS.text_sec_color(dark),
                ),
                ft.Row(
                    [
                        ft.OutlinedButton(
                            "Termos de uso",
                            icon=ft.Icons.DESCRIPTION_OUTLINED,
                            on_click=lambda _: _open_external_or_warn(terms_url, "Termos de uso"),
                        ),
                        ft.OutlinedButton(
                            "Privacidade",
                            icon=ft.Icons.POLICY_OUTLINED,
                            on_click=lambda _: _open_external_or_warn(privacy_url, "Politica de privacidade"),
                        ),
                        ft.OutlinedButton(
                            "Reembolso",
                            icon=ft.Icons.ASSIGNMENT_RETURN_OUTLINED,
                            on_click=lambda _: _open_external_or_warn(refund_url, "Politica de reembolso"),
                        ),
                    ],
                    wrap=True,
                    spacing=DS.SP_8,
                ),
                ft.Row(
                    [
                        ft.Text("Contato:", size=DS.FS_CAPTION, color=DS.text_sec_color(dark)),
                        ft.Text(support_email, size=DS.FS_CAPTION, color=DS.text_color(dark), weight=DS.FW_MED),
                        ft.TextButton(
                            "Abrir suporte",
                            icon=ft.Icons.SUPPORT_AGENT_OUTLINED,
                            on_click=lambda _: _open_external_or_warn(support_url, "Canal de suporte"),
                        ),
                    ],
                    wrap=True,
                    spacing=DS.SP_8,
                ),
            ],
            spacing=DS.SP_8,
        ),
    )

    return ft.Container(
        expand=True,
        content=ft.Column(
            [
                perfil_header,
                ds_section_title("Ferramentas", dark=dark),
                grid,
                ds_section_title("Conta", dark=dark),
                conta_section,
                ds_section_title("Legal", dark=dark),
                legal_section,
                ft.Container(height=DS.SP_32),
            ],
            spacing=DS.SP_16,
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=DS.SP_16,
    )


def _build_error_view(page: ft.Page, route: str):

    return ft.View(
        route=route,
        controls=[
            ft.Container(
                expand=True,
                alignment=ft.Alignment(0, 0),
                content=ft.Column(
                    controls=[
                        ft.Icon(ft.Icons.ERROR_OUTLINE, color=CORES["erro"], size=48),
                        ft.Text("Erro ao renderizar tela", size=22, weight=ft.FontWeight.BOLD),
                        ft.Text("Detalhes nos logs do aplicativo.", size=14),
                        ft.ElevatedButton("Voltar ao login", on_click=lambda _: page.go("/login")),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                ),
            )
        ],
        bgcolor=CORES["fundo"],
    )


def main(page: ft.Page):
    try:
        log_event("main_enter", "flet page created")
        page.title = "Quiz Vance"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.padding = 0
        page.bgcolor = CORES["fundo"]
        _apply_global_theme(page)
        is_android_runtime = bool(os.getenv("ANDROID_DATA"))
        if not is_android_runtime:
            page.window_width = 1280
            page.window_height = 820
            page.window_min_width = 560
            page.window_min_height = 520
        # Guarda global: saneia controles antes de cada update.
        raw_page_update = page.update
        if not bool(getattr(page, "_qv_safe_update_installed", False)):
            def _safe_page_update(*args, **kwargs):
                _sanitize_page_controls(page)
                return raw_page_update(*args, **kwargs)
            try:
                page.update = _safe_page_update
                setattr(page, "_qv_safe_update_installed", True)
            except Exception:
                pass

        # Recuperacao automatica para erro de layout wrap+expand.
        _recovering_wrap_error = {"active": False}

        def _on_page_error(e):
            msg = str(getattr(e, "data", "") or "")
            dbg = ""
            try:
                top_view = page.views[-1] if getattr(page, "views", None) else None
                dbg = _debug_scan_wrap_conflicts(top_view)
            except Exception:
                pass
            log_exception(Exception(f"{msg} | route={getattr(page, 'route', '')} | {dbg}"), "flet.page.on_error")
            if ("WrapParentData" not in msg) and ("FlexParentData" not in msg):
                return
            if _recovering_wrap_error["active"]:
                return
            _recovering_wrap_error["active"] = True
            try:
                _sanitize_page_controls(page)
                page.update()
            except Exception as ex_inner:
                log_exception(ex_inner, "flet.page.on_error.recover")
            finally:
                _recovering_wrap_error["active"] = False

        page.on_error = _on_page_error

        # Estado minimo; carregamos recursos pesados de forma assincrona para evitar AL_Kill.
        state = {
            "usuario": None,
            "db": None,
            "backend": None,
            "sounds": None,
            "tema_escuro": False,
            "view_cache": {},
            "last_theme": False,
            "page": page,
            "splash_done": False,
            "init_ready": False,
            "init_error": None,
            "init_task_running": False,
            "last_resize_ts": 0.0,
            "last_resize_size": None,
            "size_class": None,
            "menu_inline_open": False,
            "route_history": [],
        }

        async def _init_runtime():
            try:
                log_event("init_start", "runtime")
                state["init_error"] = None
                ensure_runtime_dirs()
                db = Database()
                db.iniciar_banco()
                state["db"] = db
                log_event("db_ready", str(get_db_path()))
                state["backend"] = BackendClient()
                state["sounds"] = create_sound_manager(page)
                state["init_ready"] = True
                log_event("init_done", "runtime_ok")
            except Exception as ex_inner:
                state["init_error"] = str(ex_inner)
                log_exception(ex_inner, "main.async_init")
            finally:
                state["init_task_running"] = False
                if not state.get("usuario"):
                    try:
                        route_change(None)
                    except Exception as ex_refresh:
                        log_exception(ex_refresh, "main.refresh_after_init")

        def _start_runtime_init():
            if state.get("db") is not None or state.get("init_task_running"):
                return
            state["init_task_running"] = True
            try:
                page.run_task(_init_runtime)
            except Exception as ex_sched:
                state["init_task_running"] = False
                state["init_error"] = str(ex_sched)
                log_exception(ex_sched, "main.schedule_init")

    except Exception as ex:
        # Qualquer falha no setup inicial deve aparecer em tela e ser logada.
        log_exception(ex, 'main.setup')
        page.views[:] = [_build_error_view(page, '/error')]
        page.update()
        return

    def log_state(event: str):
        user = state.get("usuario") or {}
        log_event(
            event,
            f"route={page.route} user_id={user.get('id')} email={user.get('email')} dark={state.get('tema_escuro')}",
        )

    def apply_theme(dark: bool):
        state["tema_escuro"] = dark
        page.theme_mode = ft.ThemeMode.DARK if dark else ft.ThemeMode.LIGHT
        page.bgcolor = _color("fundo", dark)
        page.update()

    def navigate(route: str):
        target_route = _normalize_route_path(route)
        current_route = _normalize_route_path(page.route or "/home")
        if current_route not in {"/", "/login"} and current_route != target_route:
            history = state.setdefault("route_history", [])
            if not history or history[-1] != current_route:
                history.append(current_route)
            if len(history) > 80:
                del history[:-80]
        page.go(target_route)

    async def _sync_subscription_after_login_async(local_user_id: int, backend_uid: int):
        backend_ref = state.get("backend")
        db_ref = state.get("db")
        if not backend_ref or not backend_ref.enabled() or not db_ref:
            return
        try:
            current = state.get("usuario") or {}
            if int(current.get("backend_user_id") or 0) <= 0:
                await asyncio.to_thread(
                    backend_ref.upsert_user,
                    int(backend_uid),
                    current.get("nome", ""),
                    current.get("email", ""),
                )
            b = await asyncio.to_thread(backend_ref.get_plan, int(backend_uid))
            sub = {
                "plan_code": b.get("plan_code", "free"),
                "premium_active": 1 if b.get("premium_active") else 0,
                "premium_until": b.get("premium_until"),
                "trial_used": 1 if b.get("plan_code") == "trial" else int(current.get("trial_used", 0) or 0),
            }
            await asyncio.to_thread(
                db_ref.sync_subscription_status,
                int(local_user_id),
                str(sub.get("plan_code") or "free"),
                sub.get("premium_until"),
                int(sub.get("trial_used") or 0),
            )
        except Exception as ex:
            log_exception(ex, "main._sync_subscription_after_login_async.backend")
            try:
                sub = await asyncio.to_thread(db_ref.get_subscription_status, int(local_user_id))
            except Exception:
                return

        current = state.get("usuario") or {}
        if int(current.get("id") or 0) != int(local_user_id):
            return
        current["backend_user_id"] = int(backend_uid)
        current.update(sub)
        state["view_cache"].pop("/plans", None)
        try:
            page.update()
        except Exception:
            pass

    def on_login_success(usuario: dict):
        try:
            db = state.get("db")
            if db is None:
                page.snack_bar = ft.SnackBar(content=ft.Text("Carregando recursos... tente novamente em instantes."), bgcolor=CORES["warning"], show_close_icon=True)
                page.snack_bar.open = True
                page.update()
                return
            if usuario and usuario.get("id"):
                sub = db.get_subscription_status(int(usuario["id"]))
                has_remote_sub = any(k in usuario for k in ("plan_code", "premium_active", "premium_until"))
                if has_remote_sub:
                    trial_used = int(usuario.get("trial_used", sub.get("trial_used", 0)) or 0)
                    db.sync_subscription_status(
                        int(usuario["id"]),
                        str(usuario.get("plan_code") or "free"),
                        usuario.get("premium_until"),
                        trial_used,
                    )
                    usuario["trial_used"] = trial_used
                else:
                    usuario.update(sub)
            state["usuario"] = usuario
            state["tema_escuro"] = bool(usuario.get("tema_escuro", 0))
            state["view_cache"].clear()
            state["route_history"] = []
            state["last_theme"] = state["tema_escuro"]
            sounds_ref = state.get("sounds")
            if sounds_ref:
                sounds_ref.play_level_up()
            apply_theme(state["tema_escuro"])
            onboarding_pending = int(usuario.get("onboarding_seen") or 0) == 0
            precisa_setup_inicial = (not usuario.get("oauth_google")) and (not (usuario.get("api_key") or "").strip())
            if onboarding_pending:
                navigate("/welcome")
                page.snack_bar = ft.SnackBar(
                    content=ft.Text("Primeiro login: veja o guia rapido e conheca os beneficios Free e Premium."),
                    bgcolor=CORES["warning"],
                    show_close_icon=True,
                )
                page.snack_bar.open = True
                page.update()
            else:
                navigate("/settings" if precisa_setup_inicial else "/home")
                if precisa_setup_inicial:
                    page.snack_bar = ft.SnackBar(
                        content=ft.Text("Primeiro acesso: configure provider/modelo e API key para usar IA."),
                        bgcolor=CORES["warning"],
                        show_close_icon=True,
                    )
                    page.snack_bar.open = True
                    page.update()
            backend_ref = state.get("backend")
            if backend_ref and backend_ref.enabled() and usuario and usuario.get("id"):
                backend_uid = _backend_user_id(usuario)
                usuario["backend_user_id"] = int(backend_uid)
                try:
                    page.run_task(
                        _sync_subscription_after_login_async,
                        int(usuario.get("id") or 0),
                        int(backend_uid),
                    )
                except Exception as ex:
                    log_exception(ex, "main.on_login_success.schedule_plan_sync")
            log_event("login_success", f"user_id={usuario.get('id')} email={usuario.get('email')}")
            _emit_opt_in_event(usuario, "session_started", "app_session")
            log_state("state_after_login")
        except Exception as ex:
            log_exception(ex, "main.on_login_success")
            page.snack_bar = ft.SnackBar(
                content=ft.Text("Erro ao finalizar login. Veja os logs do aplicativo."),
                bgcolor=CORES["erro"],
                show_close_icon=True,
            )
            page.snack_bar.open = True
            page.update()

    def on_logout(_):
        state["usuario"] = None
        state["view_cache"].clear()
        state["route_history"] = []
        log_event("logout", "user logout")
        log_state("state_after_logout")
        navigate("/login")

    def toggle_dark(e):
        try:
            dark = bool(e.control.value)
            apply_theme(dark)
            if state.get("usuario"):
                db = state.get("db")
                if db:
                    db.atualizar_tema_escuro(state["usuario"]["id"], dark)
                    state["usuario"]["tema_escuro"] = 1 if dark else 0
            state["view_cache"].clear()
            page.route = page.route or "/home"
            route_change(None)
            log_event("theme_toggle", f"dark={dark}")
            log_state("state_after_theme_toggle")
        except Exception as ex:
            log_exception(ex, "main.toggle_dark")

    def route_change(e):
        try:
            raw_route = page.route or "/login"
            if raw_route in ("/", "/login"):
                route = raw_route
            else:
                route = _normalize_route_path(raw_route)
                if route != raw_route:
                    page.go(route)
                    return

            # Login/landing: sem cache
            if route in ("/", "/login"):
                db_ref = state.get("db")
                if db_ref is None:
                    _start_runtime_init()
                    init_error = state.get("init_error")
                    init_running = bool(state.get("init_task_running"))
                    if init_error and not init_running:
                        error_view = ft.View(
                            route=route,
                            controls=[
                                ft.Container(
                                    expand=True,
                                    alignment=ft.Alignment(0, 0),
                                    content=ft.Column(
                                        [
                                            ft.Icon(ft.Icons.ERROR_OUTLINE, color=CORES["erro"], size=42),
                                            ft.Text("Falha na inicializacao", size=20, weight=ft.FontWeight.BOLD),
                                            ft.Text(str(init_error), size=13),
                                            ft.ElevatedButton(
                                                "Tentar novamente",
                                                on_click=lambda _: (_start_runtime_init(), route_change(None)),
                                            ),
                                        ],
                                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                        spacing=10,
                                    ),
                                )
                            ],
                            bgcolor=_color("fundo", bool(state.get("tema_escuro"))),
                        )
                        _sanitize_control_texts(error_view)
                        page.views[:] = [error_view]
                        page.update()
                        return
                    loading = ft.View(
                        route=route,
                        controls=[
                            ft.Container(
                                expand=True,
                                alignment=ft.Alignment(0, 0),
                                content=ft.Column(
                                    [
                                        ft.ProgressRing(),
                                        ft.Text("Carregando recursos..." if init_running else "Iniciando recursos..."),
                                    ],
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=12,
                                ),
                            )
                        ],
                        bgcolor=_color("fundo", bool(state.get("tema_escuro"))),
                    )
                    _sanitize_control_texts(loading)
                    page.views[:] = [loading]
                    page.update()
                    return
                login_view = LoginView(page, db_ref, on_login_success, backend=state.get("backend"))
                _style_form_controls(login_view, bool(state.get("tema_escuro")))
                _sanitize_control_texts(login_view)
                page.views[:] = [login_view]
                page.update()
                log_event("route", route)
                log_state("state_after_route")
                return

            # Protegido
            if not state["usuario"]:
                page.go("/login")
                return
            if route == "/welcome" and int((state.get("usuario") or {}).get("onboarding_seen") or 0) == 1:
                page.go("/home")
                return

            dark = state.get("tema_escuro", False)
            # invalida cache se tema mudou
            if dark != state.get("last_theme"):
                state["view_cache"].clear()
                state["last_theme"] = dark

            cache = state["view_cache"]
            view = cache.get(route)

            if view is None:
                if route == "/home":
                    body = _build_home_body(state, navigate, dark)
                elif route == "/quiz":
                    body = _build_quiz_body(state, navigate, dark)
                elif route == "/revisao":
                    body = _build_revisao_body(state, navigate, dark)
                elif route == "/mais":
                    body = _build_mais_body(state, navigate, dark, on_logout, toggle_dark)
                elif route == "/library":
                    body = _build_library_body(state, navigate, dark)
                elif route == "/study-plan":
                    body = _build_study_plan_body(state, navigate, dark)
                elif route == "/flashcards":
                    body = _build_flashcards_body(state, navigate, dark)
                elif route == "/open-quiz":
                    body = _build_open_quiz_body(state, navigate, dark)
                elif route == "/stats":
                    body = _build_stats_body(state, navigate, dark)
                elif route == "/profile":
                    body = _build_profile_body(state, navigate, dark)
                elif route == "/ranking":
                    body = _build_ranking_body(state, navigate, dark)
                elif route == "/conquistas":
                    body = _build_conquistas_body(state, navigate, dark)
                elif route == "/plans":
                    body = _build_plans_body(state, navigate, dark)
                elif route == "/welcome":
                    body = _build_onboarding_body(state, navigate, dark)
                elif route == "/settings":
                    body = _build_settings_body(state, navigate, dark)
                elif route in ("/revisao/sessao", "/revisao/erros", "/revisao/marcadas"):
                    body = build_review_session_body(state, navigate, dark, modo=route.split("/")[-1])
                elif route == "/simulado":
                    body = _build_simulado_body(state, navigate, dark)
                else:
                    page.go("/home")
                    return

                view = _build_shell_view(page, state, route, body, on_logout, dark, toggle_dark)
                form_heavy_routes = {
                    "/quiz",
                    "/flashcards",
                    "/open-quiz",
                    "/study-plan",
                    "/settings",
                    "/plans",
                    "/simulado",
                    "/library",
                }
                if route in form_heavy_routes:
                    _style_form_controls(view, dark)
                _sanitize_control_texts(view)
                # Rotas dinamicas nao devem ser cacheadas (estado interno muda)
                _no_cache_routes = {"/quiz", "/flashcards", "/open-quiz", "/settings", "/library",
                                    "/revisao", "/revisao/sessao", "/revisao/erros", "/revisao/marcadas",
                                    "/mais", "/simulado"}
                if route not in _no_cache_routes:
                    cache[route] = view

            # Evita piscadas: sÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³ troca se for outra instÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ncia
            if page.views and page.views[-1] is view:
                log_event("route_cached", route)
                return
            page.views[:] = [view]
            page.update()
            log_event("route", route)
            log_state("state_after_route")
        except Exception as ex:
            import traceback
            print(f"\n{'='*60}")
            print(f"[ERRO FATAL] Rota: {page.route}")
            traceback.print_exc()
            print(f"{'='*60}\n")
            log_exception(ex, "main.route_change")
            page.views.clear()
            page.views.append(_build_error_view(page, page.route))
            page.update()

    def view_pop(e):
        try:
            history = state.setdefault("route_history", [])
            current = _normalize_route_path(page.route or "/home")
            while history:
                prev = _normalize_route_path(history.pop())
                if prev and prev not in {"/", "/login"} and prev != current:
                    page.go(prev)
                    return
            page.go("/home" if state["usuario"] else "/login")
        except Exception as ex:
            log_exception(ex, "main.view_pop")
            page.go("/login")

    def on_resized(e):
        try:
            now = time.time()
            width = int(_screen_width(page))
            height = int(_screen_height(page))
            size = (width, height)
            size_class = (width < 980, width < 760)
            last_ts = float(state.get("last_resize_ts") or 0.0)
            last_size = state.get("last_resize_size")
            last_size_class = state.get("size_class")
            # Ignora eventos que nao mudam o layout responsivo.
            if last_size_class == size_class and (now - last_ts) < 1.0:
                return
            # Debounce agressivo para reduzir reconstrucoes da UI.
            if last_size == size and (now - last_ts) < 0.35:
                return
            if (now - last_ts) < 0.20:
                return
            state["last_resize_ts"] = now
            state["last_resize_size"] = size
            state["size_class"] = size_class
            route = page.route or "/login"
            state["view_cache"].pop(route, None)
            route_change(None)
        except Exception as ex:
            log_exception(ex, "main.on_resized")

    page.on_route_change = route_change
    page.on_view_pop = view_pop
    page.on_resized = on_resized
    page.update()
    # Splash e runtime em paralelo para reduzir percepcao de lentidao:
    # 1) mostra splash
    # 2) inicia runtime em background durante o splash
    # 3) navega para /login com runtime ja adiantado
    is_android = bool(os.getenv("ANDROID_DATA"))
    _start_runtime_init()
    splash_view, logo_box, tagline = _build_splash(page, navigate, state["tema_escuro"])
    page.views[:] = [splash_view]
    page.update()

    async def run_splash():
        # Android: splash curta e estatica para reduzir risco de black screen.
        if is_android:
            # Keep Android splash static and visible (no fade), then navigate.
            logo_box.opacity = 1
            logo_box.width = 200
            logo_box.height = 200
            tagline.opacity = 1
            if splash_view.controls and hasattr(splash_view.controls[0], "content"):
                splash_root = splash_view.controls[0].content
                splash_root.opacity = 1
            page.update()
            await asyncio.sleep(1.2)
            page.go("/login")
            page.update()
            return

        # Desktop: fade curto
        logo_box.opacity = 1
        logo_box.width = 200
        logo_box.height = 200
        tagline.opacity = 1
        page.update()
        await asyncio.sleep(0.95)
        # fade out curto
        if splash_view.controls and hasattr(splash_view.controls[0], "content"):
            splash_root = splash_view.controls[0].content
            splash_root.opacity = 0
            page.update()
        await asyncio.sleep(0.12)
        page.go("/login")
        page.update()
    try:
        page.run_task(run_splash)
    except Exception as ex:
        # Fallback para versoes de Flet com comportamento diferente em run_task.
        log_exception(ex, "main.run_splash")
        page.go("/login")







