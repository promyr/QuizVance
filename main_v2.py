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
from typing import Optional

from config import CORES, AI_PROVIDERS, DIFICULDADES, get_level_info
from core.database_v2 import Database
from core.backend_client import BackendClient
from core.error_monitor import log_exception, log_event
from core.app_paths import ensure_runtime_dirs, get_db_path
from core.ai_service_v2 import AIService, create_ai_provider
from core.sounds import create_sound_manager
from core.library_service import LibraryService
from ui.views.login_view_v2 import LoginView

APP_ROUTES = [
    ("/home", "Inicio", ft.Icons.HOME_OUTLINED),
    ("/quiz", "Questões", ft.Icons.QUIZ_OUTLINED),
    ("/flashcards", "Flashcards", ft.Icons.STYLE_OUTLINED),
    ("/open-quiz", "Dissertativo", ft.Icons.EDIT_NOTE_OUTLINED),
    ("/library", "Biblioteca", ft.Icons.LOCAL_LIBRARY_OUTLINED),
    ("/study-plan", "Plano", ft.Icons.CALENDAR_MONTH_OUTLINED),
    ("/stats", "Estatisticas", ft.Icons.INSIGHTS_OUTLINED),
    ("/profile", "Perfil", ft.Icons.PERSON_OUTLINE),
    ("/ranking", "Ranking", ft.Icons.EMOJI_EVENTS_OUTLINED),
    ("/conquistas", "Conquistas", ft.Icons.MILITARY_TECH_OUTLINED),
    ("/plans", "Planos", ft.Icons.STARS_OUTLINED),
    ("/settings", "Configuracoes", ft.Icons.SETTINGS_OUTLINED),
]


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
    try:
        return AIService(create_ai_provider(provider_type, api_key, model_value))
    except Exception as ex:
        log_exception(ex, "main._create_user_ai_service")
        return None


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
    control.value = message
    control.color = palette.get(tone, palette["info"])


def _wrap_study_content(content: ft.Control, dark: bool):
    return ft.Container(
        expand=True,
        bgcolor=_color("fundo", dark),
        padding=12,
        content=ft.Container(
            alignment=ft.Alignment(0, -1),  # top-center alignment (compatible)
            expand=True,
            content=ft.Container(
                expand=True,
                content=content,
            ),
        ),
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
            page.overlay = []
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
    # FORCAR DESKTOP LAYOUT (1280px) EM TODAS AS PLATAFORMAS CONFORME SOLICITADO
    return 1280.0


def _screen_height(page: ft.Page) -> float:
    height = getattr(page, "height", None)
    if height:
        try:
            height_value = float(height)
            if height_value > 0:
                return height_value
        except Exception:
            pass

    window_height = getattr(page, "window_height", None)
    if window_height:
        try:
            window_value = float(window_height)
            if window_value > 0:
                return window_value
        except Exception:
            pass

    return 820.0


def _format_datetime_label(value: Optional[str]) -> str:
    if not value:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.datetime.strptime(raw, fmt)
            return dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            continue
    return raw


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
    page = state.get("page")
    screen_w = _screen_width(page) if page else 1280
    compact = screen_w < 1100
    mobile = screen_w < 760

    usuario = state.get("usuario") or {}
    db = state.get("db")
    info_nivel = get_level_info(usuario.get("xp", 0))
    topicos_revisao = []
    revisoes_pendentes = 0
    progresso_diario = {
        "meta_questoes": int(usuario.get("meta_questoes_diaria") or 20),
        "questoes_respondidas": 0,
        "acertos": 0,
        "progresso_meta": 0.0,
        "streak_dias": int(usuario.get("streak_dias") or 0),
    }
    if db and usuario.get("id"):
        try:
            topicos_revisao = db.topicos_revisao(usuario["id"], limite=3)
            revisoes_pendentes = db.revisoes_pendentes(usuario["id"])
            progresso_diario = db.obter_progresso_diario(usuario["id"])
        except Exception as ex:
            log_exception(ex, "main._build_home_body.topicos_revisao")

    cards = [
        ("Questões", "Questoes objetivas com IA", "/quiz", ft.Icons.QUIZ),
        ("Flashcards", "Revisao rapida por cards", "/flashcards", ft.Icons.STYLE),
        ("Dissertativo", "Resposta aberta com feedback", "/open-quiz", ft.Icons.EDIT_NOTE),
        ("Biblioteca", "Gerencie seus PDFs e textos", "/library", ft.Icons.LOCAL_LIBRARY),
        ("Plano", "Plano semanal adaptativo", "/study-plan", ft.Icons.CALENDAR_MONTH),
        ("Planos", "Free, Premium 15 e Premium 30", "/plans", ft.Icons.STARS),
        ("Estatisticas", "Evolucao e desempenho", "/stats", ft.Icons.INSIGHTS),
        ("Perfil", "Dados da conta e preferencias", "/profile", ft.Icons.PERSON),
        ("Ranking", "Competicao entre usuarios", "/ranking", ft.Icons.EMOJI_EVENTS),
        ("Conquistas", "Medalhas e metas", "/conquistas", ft.Icons.MILITARY_TECH),
        ("Configuracoes", "Ajustes do aplicativo", "/settings", ft.Icons.SETTINGS),
    ]

    horizontal_padding = 8 if mobile else (12 if compact else 16)
    if screen_w >= 1160:
        cards_col = 4
    else:
        cards_col = 6
    card_height = 178 if mobile else 190

    card_controls = []
    for title, desc, route, icon in cards:
        card_controls.append(
            ft.Container(
                col=cards_col,
                height=card_height,
                padding=12 if mobile else 14,
                border_radius=14,
                bgcolor=_color("card", dark),
                border=ft.border.all(1, ft.Colors.with_opacity(0.08, _color("texto", dark))),
                content=ft.Column(
                    [
                        ft.Column(
                            [
                                ft.Icon(icon, color=CORES["primaria"], size=24 if mobile else 26),
                                ft.Text(
                                    title,
                                    size=14 if mobile else 16,
                                    weight=ft.FontWeight.BOLD,
                                    color=_color("texto", dark),
                                    max_lines=2,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                ft.Text(
                                    desc,
                                    size=11 if mobile else 12,
                                    color=_color("texto_sec", dark),
                                    max_lines=2,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                            spacing=6,
                            expand=True,
                        ),
                        ft.Row(
                            [
                                ft.ElevatedButton(
                                    "Abrir",
                                    width=88 if mobile else 96,
                                    height=34 if mobile else 36,
                                    on_click=lambda _, r=route: navigate(r),
                                )
                            ],
                            alignment=ft.MainAxisAlignment.START,
                        ),
                    ],
                    spacing=8,
                    expand=True,
                ),
            )
        )

    revisao_controls = []
    if not topicos_revisao:
        revisao_controls.append(
            ft.Text(
                "Resolva questoes para receber recomendacoes de revisao.",
                size=12,
                color=_color("texto_sec", dark),
            )
        )
    else:
        for i, item in enumerate(topicos_revisao, 1):
            revisao_controls.append(
                ft.Row(
                    [
                        ft.Text(f"{i}. {item.get('tema', 'Geral')}", weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                        ft.Container(expand=True),
                        ft.Text(
                            f"{int(item.get('erros_total', 0))} erros em {int(item.get('tentativas_total', 0))} tentativas",
                            size=12,
                            color=_color("texto_sec", dark),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    wrap=True,
                )
            )

    content_column = ft.Column(
        controls=[
            ft.Text(
                f"Bem-vindo, {usuario.get('nome', 'Usuario')}!",
                size=24 if mobile else 28,
                weight=ft.FontWeight.BOLD,
                color=_color("texto", dark),
            ),
            ft.Container(
                padding=12,
                border_radius=12,
                bgcolor=_color("card", dark),
                border=ft.border.all(1, ft.Colors.with_opacity(0.08, _color("texto", dark))),
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(f"Nivel {info_nivel['atual']['nome']}", weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                ft.Text(f"{usuario.get('xp', 0)} XP", size=12, color=_color("texto_sec", dark)),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.ProgressBar(
                            value=info_nivel["progresso"],
                            color=CORES.get(info_nivel["atual"]["cor"], CORES["primaria"]),
                            bgcolor=ft.Colors.with_opacity(0.2, CORES["primaria"]),
                            height=8,
                        ),
                        ft.Text(
                            f"Faltam {info_nivel['xp_necessario']} XP para {info_nivel['proximo']['nome']}" if info_nivel["proximo"] else "Nivel maximo!",
                            size=11,
                            color=_color("texto_sec", dark),
                        ),
                    ],
                    spacing=4,
                ),
            ),
            ft.Card(
                elevation=1,
                content=ft.Container(
                    padding=12,
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text("Missao diaria", size=16, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                    ft.Text(f"Streak: {int(progresso_diario.get('streak_dias', 0))} dia(s)", size=12, color=_color("texto_sec", dark)),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                wrap=True,
                            ),
                            ft.ProgressBar(
                                value=float(progresso_diario.get("progresso_meta", 0.0)),
                                color=CORES["primaria"],
                                bgcolor=ft.Colors.with_opacity(0.18, CORES["primaria"]),
                                height=8,
                            ),
                            ft.Text(
                                f"{int(progresso_diario.get('questoes_respondidas', 0))}/{int(progresso_diario.get('meta_questoes', 20))} questoes hoje"
                                f" | Acertos: {int(progresso_diario.get('acertos', 0))}",
                                size=12,
                                color=_color("texto_sec", dark),
                            ),
                            ft.Row(
                                [
                                    ft.ElevatedButton("Continuar estudo", icon=ft.Icons.PLAY_ARROW, on_click=lambda _: _start_prioritized_session(state, navigate)),
                                    ft.TextButton("Abrir Questões", icon=ft.Icons.QUIZ, on_click=lambda _: navigate("/quiz")),
                                ],
                                wrap=True,
                                spacing=10,
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
                            ft.Row(
                                [
                                    ft.Text("Proximos 3 topicos para revisar", size=16, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                    ft.ElevatedButton("Sessao rapida", icon=ft.Icons.PLAY_ARROW, on_click=lambda _: navigate("/quiz")),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                wrap=True,
                            ),
                            ft.Text(f"Revisoes pendentes agora: {revisoes_pendentes}", size=12, color=_color("texto_sec", dark)),
                            *revisao_controls,
                            ft.Row(
                                [
                                    ft.ElevatedButton(
                                        "Estudar agora (priorizado)",
                                        icon=ft.Icons.AUTO_AWESOME,
                                        on_click=lambda _: _start_prioritized_session(state, navigate),
                                    ),
                                ],
                                wrap=True,
                            ),
                        ],
                        spacing=8,
                    ),
                ),
            ),
            ft.Container(height=6),
            ft.ResponsiveRow(
                controls=card_controls,
                spacing=10 if mobile else 12,
                run_spacing=10 if mobile else 12,
            ),
        ],
        spacing=10 if mobile else 12,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    return ft.Container(
        expand=True,
        alignment=ft.Alignment(0, -1),
        padding=ft.padding.symmetric(horizontal=horizontal_padding, vertical=10 if mobile else 14),
        content=ft.Container(
            expand=True,
            content=content_column,
        ),
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
        "Questões": [
            "Escolha categoria e dificuldade para gerar questoes.",
            "Cada rodada traz 5 questoes com feedback imediato.",
            "Use 'Reforco' para ver explicacoes detalhadas."
        ],
        "Flashcards": [
            "Selecione tema e gere baralho com IA.",
            "Marque como 'Lembrei' ou 'Rever' para espacamento.",
            "Exportar para revisao offline (CSV em breve)."
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
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(p.get("titulo", "Pacote"), weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                    ft.Text(f"{qcount} questoes • {fcount} flashcards", size=12, color=_color("texto_sec", dark)),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.TextButton(
                                "Usar no Quiz",
                                icon=ft.Icons.PLAY_ARROW,
                                on_click=lambda _, d=dados: _start_quiz_from_package(d),
                            ),
                        ]
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
            service = _create_user_ai_service(user)
            summary = {"resumo": "Resumo indisponivel.", "topicos": []}
            questoes = []
            flashcards = []
            if service:
                summary = await asyncio.to_thread(service.generate_study_summary, chunks, file_name, 1)
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
                        {
                            "enunciado": q.get("pergunta", ""),
                            "alternativas": q.get("opcoes", []),
                            "correta_index": q.get("correta_index", 0),
                        }
                    )
                flashcards = await asyncio.to_thread(service.generate_flashcards, chunks, 5, 1)
            if not questoes:
                questoes = random.sample(DEFAULT_QUIZ_QUESTIONS, min(3, len(DEFAULT_QUIZ_QUESTIONS)))
            pacote = {
                "resumo": summary.get("resumo", ""),
                "topicos": summary.get("topicos", []),
                "questoes": questoes,
                "flashcards": flashcards,
            }
            db.salvar_study_package(user["id"], f"Pacote - {file_name}", file_name, pacote)
            status_text.value = "Pacote gerado e salvo."
            status_text.color = CORES["sucesso"]
            _refresh_packages()
        except Exception as ex:
            log_exception(ex, "_generate_package_async")
            status_text.value = "Falha ao gerar pacote."
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
                            content=ft.Row([
                                ft.Icon(ft.Icons.PICTURE_AS_PDF if nome.endswith(".pdf") else ft.Icons.DESCRIPTION, color=CORES["primaria"]),
                                ft.Column([
                                    ft.Text(nome, weight=ft.FontWeight.BOLD, color=_color("texto", dark), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                    ft.Text(f"Adicionado em {date_str} • {arq.get('total_paginas', 0)} paginas", size=12, color=_color("texto_sec", dark))
                                ], expand=True, spacing=2),
                                btn_package,
                                btn_delete
                            ])
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
                            ]),
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
    # Splash usa fundo escuro fixo para realÃ§ar a logo
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
                "prova_deadline": None,
                "confirmados": set(),
                "ultimo_filtro": {},
                "generation_token": 0,
                "target_total": 0,
                "prefetch_seed": [],
                "prefetch_busy": False,
            },
        }
        state["quiz_session"] = session

    questoes = session["questoes"]
    estado = session["estado"]
    estado.setdefault("respostas", {})
    estado.setdefault("corrigido", False)
    estado.setdefault("upload_texts", [])
    estado.setdefault("upload_names", [])
    estado.setdefault("favoritas", set())
    estado.setdefault("marcadas_erro", set())
    estado.setdefault("current_idx", 0)
    estado.setdefault("feedback_imediato", True)
    estado.setdefault("simulado_mode", False)
    estado.setdefault("modo_continuo", False)
    estado.setdefault("start_time", None)
    estado.setdefault("prova_deadline", None)
    estado.setdefault("confirmados", set())
    estado.setdefault("ultimo_filtro", {})
    estado.setdefault("generation_token", 0)
    estado.setdefault("target_total", 0)
    estado.setdefault("prefetch_seed", [])
    estado.setdefault("prefetch_busy", False)
    estado.setdefault("last_base_content", [])
    estado.setdefault("last_tema", "")
    cards_column = ft.Column(
        spacing=12,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )
    resultado = ft.Text("", weight=ft.FontWeight.BOLD)
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
    upload_info = ft.Text("Nenhum material enviado.", size=12, weight=ft.FontWeight.W_400, color=_color("texto_sec", dark))
    ai_enabled = bool(_create_user_ai_service(user))

    dificuldade_padrao = "intermediario" if "intermediario" in DIFICULDADES else next(iter(DIFICULDADES))
    difficulty_dropdown = ft.Dropdown(
        label="Dificuldade",
        width=160 if compact else 220,
        options=[ft.dropdown.Option(key=key, text=cfg["nome"]) for key, cfg in DIFICULDADES.items()],
        value=dificuldade_padrao,
    )
    quiz_count_dropdown = ft.Dropdown(
        label="Quantidade",
        width=140 if compact else 180,
        options=[
            ft.dropdown.Option(key="10", text="10 questoes"),
            ft.dropdown.Option(key="20", text="20 questoes"),
            ft.dropdown.Option(key="30", text="30 questoes"),
            ft.dropdown.Option(key="cont", text="Cont\u00ednuo (stream)"),
        ],
        value="10",
    )
    if not _is_premium_active(user):
        quiz_count_dropdown.options = [opt for opt in quiz_count_dropdown.options if opt.key != "cont"]
        quiz_count_dropdown.value = quiz_count_dropdown.value if quiz_count_dropdown.value != "cont" else "10"
    def _on_count_change(e):
        val = e.control.value or "10"
        preview_count_text.value = "\u221e" if val == "cont" else str(val)
        if page:
            page.update()
    quiz_count_dropdown.on_change = _on_count_change
    session_mode_dropdown = ft.Dropdown(
        label="Sessao",
        width=170 if compact else 220,
        options=[
            ft.dropdown.Option(key="nova", text="Nova sessao"),
            ft.dropdown.Option(key="erradas", text="Erradas recentes"),
            ft.dropdown.Option(key="favoritas", text="Favoritas"),
            ft.dropdown.Option(key="nao_resolvidas", text="Nao resolvidas"),
        ],
        value="nova",
    )
    feedback_imediato_switch = ft.Switch(label="Feedback imediato", value=True, visible=False)
    simulado_mode_switch = ft.Switch(label="Modo prova", value=False)
    simulado_tempo_field = ft.TextField(label="Tempo prova (min)", width=140 if compact else 180, hint_text="30", value="30")

    def _on_simulado_toggle(e):
        sim = bool(getattr(e.control, "value", False))
        estado["simulado_mode"] = sim
        estado["feedback_imediato"] = not sim
        feedback_imediato_switch.value = not sim
        if page:
            page.update()

    simulado_mode_switch.on_change = _on_simulado_toggle
    save_filter_name = ft.TextField(label="Salvar filtro como", width=190 if compact else 240, hint_text="Ex.: Revisao Direito")
    saved_filters_dropdown = ft.Dropdown(label="Filtros salvos", width=220 if compact else 280, options=[])

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
    if isinstance(preset, dict):
        topic_field.value = str(preset.get("topic") or "")
        difficulty_dropdown.value = str(preset.get("difficulty") or dificuldade_padrao)
        quiz_count_dropdown.value = str(preset.get("count") or "10")
        preview_count_text.value = "\u221e" if quiz_count_dropdown.value == "cont" else str(quiz_count_dropdown.value or "10")
        session_mode_dropdown.value = str(preset.get("session_mode") or "nova")
        simulado_mode_switch.value = bool(preset.get("simulado_mode", False))
        status_text.value = str(preset.get("reason") or "Preset aplicado.")
    estado["simulado_mode"] = bool(simulado_mode_switch.value)
    estado["feedback_imediato"] = not estado["simulado_mode"]

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
        width=220 if compact else 300,
        options=library_opts,
        disabled=not library_opts
    )
    library_dropdown.on_change = _on_library_select

    def _normalize_question_for_ui(q: dict) -> Optional[dict]:
        if not isinstance(q, dict):
            return None
        enunciado = (q.get("enunciado") or q.get("pergunta") or "").strip()
        alternativas = q.get("alternativas") or q.get("opcoes") or []
        if not enunciado or not isinstance(alternativas, list) or len(alternativas) < 2:
            return None
        alternativas = [str(a).strip() for a in alternativas if str(a).strip()]
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
            out["explicacao"] = str(q.get("explicacao"))
        if q.get("_meta"):
            out["_meta"] = q.get("_meta")
        return out

    def _cache_topic_name(topic_value: str) -> str:
        tema = (topic_value or "").strip()
        return tema if tema else "Geral"

    def _append_unique_questions(target: list, candidates: list) -> int:
        seen = {
            str((item.get("enunciado") or item.get("pergunta") or "")).strip().lower()
            for item in target
            if isinstance(item, dict)
        }
        added = 0
        for raw in candidates or []:
            qnorm = _normalize_question_for_ui(raw)
            if not qnorm:
                continue
            key = qnorm.get("enunciado", "").strip().lower()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            target.append(qnorm)
            added += 1
        return added

    def _save_questions_to_cache(topic_value: str, difficulty_key: str, questions_list: list):
        if not db:
            return
        tema_cache = _cache_topic_name(topic_value)
        for q in questions_list:
            try:
                db.salvar_questao_cache(tema_cache, difficulty_key, q)
            except Exception as ex:
                log_exception(ex, "main._build_quiz_body.salvar_questao_cache")

    def _get_cached_questions(topic_value: str, difficulty_key: str, limit: int) -> list:
        if not db or limit <= 0:
            return []
        try:
            cached = db.listar_questoes_cache(_cache_topic_name(topic_value), difficulty_key, limit)
            return [q for q in (_normalize_question_for_ui(x) for x in cached) if q]
        except Exception as ex:
            log_exception(ex, "main._build_quiz_body.listar_questoes_cache")
            return []

    def _next_generation_token() -> int:
        token = int(estado.get("generation_token", 0) or 0) + 1
        estado["generation_token"] = token
        return token

    def _is_generation_token_active(token: int) -> bool:
        return int(estado.get("generation_token", 0) or 0) == int(token or 0)

    def _consume_prefetch_seed(limit: int) -> list:
        if limit <= 0:
            return []
        seed = list(estado.get("prefetch_seed") or [])
        if not seed:
            return []
        taken = seed[:limit]
        estado["prefetch_seed"] = seed[limit:]
        return taken

    async def _fetch_quiz_chunk_async(topic_value: str, referencia_list: list, difficulty_key: str, quantidade: int) -> list:
        qtd = max(1, min(10, int(quantidade or 1)))
        bloco = []

        seed_items = _consume_prefetch_seed(qtd)
        if seed_items:
            _append_unique_questions(bloco, seed_items)

        restante = qtd - len(bloco)
        if restante > 0:
            cached = _get_cached_questions(topic_value, difficulty_key, restante)
            if cached:
                _append_unique_questions(bloco, cached)

        restante = qtd - len(bloco)
        if restante > 0:
            gen_profile = _generation_profile(user, "quiz")
            service = _create_user_ai_service(user, force_economic=bool(gen_profile.get("force_economic")))
            if service and (topic_value or referencia_list) and not _is_ai_quota_exceeded(service):
                try:
                    lote = await asyncio.to_thread(
                        service.generate_quiz_batch,
                        referencia_list or None,
                        topic_value or None,
                        DIFICULDADES.get(difficulty_key, {}).get("nome", "Intermediario"),
                        restante,
                        1,
                    )
                    before = len(bloco)
                    if _append_unique_questions(bloco, lote):
                        _save_questions_to_cache(topic_value, difficulty_key, bloco[before:])
                except Exception as ex:
                    log_exception(ex, "main._build_quiz_body._fetch_quiz_chunk_async")

        while len(bloco) < qtd:
            bloco.append(dict(random.choice(DEFAULT_QUIZ_QUESTIONS)))
        return bloco[:qtd]

    async def _complete_quiz_generation_async(token: int, target_total: int):
        if not page or target_total <= 0:
            return
        while _is_generation_token_active(token) and len(questoes) < target_total:
            restante = target_total - len(questoes)
            lote = 10 if restante >= 10 else (5 if restante >= 5 else restante)
            filtro = estado.get("ultimo_filtro") or {}
            bloco = await _fetch_quiz_chunk_async(
                (filtro.get("topic") or "").strip(),
                list(filtro.get("referencia") or []),
                filtro.get("difficulty") or dificuldade_padrao,
                lote,
            )
            added = _append_unique_questions(questoes, bloco)
            if added <= 0:
                break
            _set_feedback_text(status_text, f"Carregando ... {len(questoes)}/{target_total}", "info")
            _refresh_status_boxes()
            _rebuild_cards()
            page.update()

        if _is_generation_token_active(token) and len(questoes) < target_total:
            while len(questoes) < target_total:
                questoes.append(dict(random.choice(DEFAULT_QUIZ_QUESTIONS)))
            _rebuild_cards()

        if _is_generation_token_active(token):
            _set_feedback_text(status_text, "Pronto.", "success")
            _refresh_status_boxes()
            page.update()

    async def _ensure_quiz_buffer_async(token: int):
        if not page or not estado.get("modo_continuo"):
            return
        if not _is_generation_token_active(token):
            return
        if estado.get("prefetch_busy"):
            return

        estado["prefetch_busy"] = True
        try:
            while _is_generation_token_active(token) and estado.get("modo_continuo"):
                ahead = max(0, len(questoes) - int(estado.get("current_idx", 0)) - 1)
                need = max(0, 2 - ahead)
                if need <= 0:
                    break
                filtro = estado.get("ultimo_filtro") or {}
                bloco = await _fetch_quiz_chunk_async(
                    (filtro.get("topic") or "").strip(),
                    list(filtro.get("referencia") or []),
                    filtro.get("difficulty") or dificuldade_padrao,
                    need,
                )
                added = _append_unique_questions(questoes, bloco)
                while added < need:
                    questoes.append(dict(random.choice(DEFAULT_QUIZ_QUESTIONS)))
                    added += 1
                _set_feedback_text(status_text, "Fluxo continuo: 2 proximas questoes prontas.", "info")
                _refresh_status_boxes()
                _rebuild_cards()
                page.update()
        finally:
            estado["prefetch_busy"] = False

    def _request_quiz_buffer():
        if not page or not estado.get("modo_continuo"):
            return
        ahead = max(0, len(questoes) - int(estado.get("current_idx", 0)) - 1)
        if ahead < 2:
            page.run_task(_ensure_quiz_buffer_async, int(estado.get("generation_token", 0) or 0))

    def _current_filter_payload() -> dict:
        return {
            "topic": (topic_field.value or "").strip(),
            "difficulty": difficulty_dropdown.value or dificuldade_padrao,
            "count": str(quiz_count_dropdown.value or "5"),
            "session_mode": session_mode_dropdown.value or "nova",
            "feedback_imediato": not bool(simulado_mode_switch.value),
            "simulado_mode": bool(simulado_mode_switch.value),
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
        if quiz_count_dropdown.value == "cont" and not _is_premium_active(user):
            quiz_count_dropdown.value = "10"
        session_mode_dropdown.value = filtro.get("session_mode", "nova")
        simulado_mode_switch.value = bool(filtro.get("simulado_mode", False))
        feedback_imediato_switch.value = not bool(simulado_mode_switch.value)
        estado["simulado_mode"] = bool(simulado_mode_switch.value)
        estado["feedback_imediato"] = not estado["simulado_mode"]
        status_text.value = f"Filtro aplicado: {item.get('nome', '')}"
        if page:
            page.update()

    def _save_current_filter(_):
        if not db or not user.get("id"):
            return
        nome = (save_filter_name.value or "").strip()
        if not nome:
            status_text.value = "Informe um nome para salvar o filtro."
            if page:
                page.update()
            return
        try:
            db.salvar_filtro_quiz(user["id"], nome, _current_filter_payload())
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

    timer_task_ref = {"task": None}

    def _update_session_meta():
        total = len(questoes)
        respondidas = len([k for k, v in estado["respostas"].items() if v is not None])
        progresso_text.value = f"{respondidas}/{total} respondidas"
        if estado.get("prova_deadline"):
            restante = int(max(0, estado["prova_deadline"] - time.monotonic()))
            tempo_text.value = f"Restante: {restante // 60:02d}:{restante % 60:02d}"
        elif estado.get("start_time"):
            elapsed = int(max(0, time.monotonic() - estado["start_time"]))
            tempo_text.value = f"Tempo: {elapsed // 60:02d}:{elapsed % 60:02d}"
        else:
            tempo_text.value = "Tempo: 00:00"

    def _refresh_status_boxes():
        status_box.visible = bool(status_text.value.strip())
        status_estudo_box.visible = bool(status_estudo.value.strip())

    async def _cronometro_task():
        while estado.get("start_time") and not estado.get("corrigido"):
            _update_session_meta()
            if estado.get("prova_deadline"):
                restante = int(max(0, estado["prova_deadline"] - time.monotonic()))
                if restante <= 0:
                    status_estudo.value = "Tempo esgotado. Prova encerrada."
                    _refresh_status_boxes()
                    if page:
                        page.update()
                    corrigir(None, forcar_timeout=True)
                    break
            if page:
                page.update()
            await asyncio.sleep(1)

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
        estado["ultimo_tema"] = topic_field.value or ""
        estado["ultima_referencia"] = referencia_field.value or ""
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
        pergunta_txt = questao["enunciado"]
        correta_idx = questao.get("correta_index", 0)
        resposta_txt = questao["alternativas"][correta_idx]
        
        # Chamar AI
        service = _create_user_ai_service(user)
        explicacao = "Erro ao conectar com IA."
        if service:
            explicacao = await asyncio.to_thread(service.explain_simple, pergunta_txt, resposta_txt, 1)
            
        # Fechar loading e mostrar resultado
        _close_dialog_compat(page, dlg)
        
        await asyncio.sleep(0.1)
        
        res_dlg = ft.AlertDialog(
            title=ft.Text("Explicação Simplificada"),
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
        estado["current_idx"] = min(len(questoes) - 1, estado["current_idx"] + 1)
        _request_quiz_buffer()
        _rebuild_cards()
        if page:
            page.update()

    def _prev_question(_=None):
        if not questoes:
            return
        estado["current_idx"] = max(0, estado["current_idx"] - 1)
        _rebuild_cards()
        if page:
            page.update()

    def _skip_question(_=None):
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

    def _rebuild_cards():
        cards_column.controls.clear()
        sw = _screen_width(page) if page else 1280
        q_font = 22 if sw < 900 else (26 if sw < 1280 else 30)
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
            _refresh_status_boxes()
            return
        # questoes nao esta vazio (verificado acima com early return)
        idx = int(max(0, min(len(questoes) - 1, estado.get("current_idx", 0))))
        estado["current_idx"] = idx
        pergunta = questoes[idx]
        options = []
        correta_idx = pergunta.get("correta_index", 0)
        selected = estado["respostas"].get(idx)
        is_corrigido = estado["corrigido"]
        if not estado.get("simulado_mode") and idx in estado["confirmados"]:
            is_corrigido = True

        for i, alt in enumerate(pergunta["alternativas"]):
            fill_color = CORES["primaria"]
            opacity = 1.0
            if is_corrigido and selected is not None:
                if i == correta_idx:
                    fill_color = CORES["sucesso"]
                elif i == selected and i != correta_idx:
                    fill_color = CORES["erro"]
                else:
                    opacity = 0.55
            options.append(ft.Radio(value=str(i), label=alt, fill_color=fill_color, opacity=opacity))

        def _on_change(e):
            if estado["corrigido"]:
                return
            valor = getattr(e.control, "value", None)
            estado["respostas"][idx] = int(valor) if valor is not None else None
            if idx in estado["confirmados"]:
                estado["confirmados"].discard(idx)
            _update_session_meta()
            if page:
                page.update()

        header_badges = []
        if idx in estado["favoritas"]:
            header_badges.append(ft.Icon(ft.Icons.STAR, color=CORES["warning"], size=18))
        if idx in estado["marcadas_erro"]:
            header_badges.append(ft.Icon(ft.Icons.FLAG, color=CORES["erro"], size=18))

        card_content_controls = [
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
                    pergunta["enunciado"],
                    weight=ft.FontWeight.BOLD,
                    color=_color("texto", dark),
                    size=q_font,
                    text_align=ft.TextAlign.CENTER,
                ),
            ),
            ft.RadioGroup(
                value=str(selected) if selected is not None else None,
                on_change=_on_change,
                content=ft.Column(options, spacing=4),
                disabled=estado["corrigido"],
            ),
        ]

        if (estado["corrigido"] or (estado.get("feedback_imediato") and not estado.get("simulado_mode"))) and selected is not None:
            feedback_color = CORES["sucesso"] if selected == correta_idx else CORES["erro"]
            feedback_msg = "Correto!" if selected == correta_idx else "Incorreto."
            card_content_controls.append(
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

        card_content_controls.append(
            ft.Row(
                [
                    ft.TextButton("Anterior", icon=ft.Icons.CHEVRON_LEFT, on_click=_prev_question),
                    ft.TextButton("Pular", icon=ft.Icons.SKIP_NEXT, on_click=_skip_question),
                    ft.TextButton(
                        "Proxima",
                        icon=ft.Icons.CHEVRON_RIGHT,
                        on_click=_next_question,
                        disabled=idx not in estado["confirmados"],
                    ),
                    ft.OutlinedButton(
                        "Confirmar resposta",
                        icon=ft.Icons.CHECK_CIRCLE,
                        on_click=lambda _: _confirmar(),
                        disabled=selected is None or idx in estado["confirmados"],
                    ),
                    ft.Container(expand=True),
                    ft.TextButton(
                        "Favoritar",
                        icon=ft.Icons.STAR if idx in estado["favoritas"] else ft.Icons.STAR_BORDER,
                        on_click=_toggle_favorita,
                    ),
                    ft.TextButton(
                        "Marcar erro",
                        icon=ft.Icons.FLAG if idx in estado["marcadas_erro"] else ft.Icons.FLAG_OUTLINED,
                        on_click=_toggle_marcada_erro,
                    ),
                ],
                spacing=6,
                wrap=True,
                alignment=ft.MainAxisAlignment.CENTER,
            )
        )

        note_default = ""
        if db and user.get("id"):
            try:
                note_default = db.obter_nota_questao(user["id"], pergunta)
            except Exception as ex:
                log_exception(ex, "main._build_quiz_body.obter_nota_questao")
        note_field = ft.TextField(
            label="Anotacao desta questao (privada)",
            value=note_default,
            multiline=True,
            min_lines=2,
            max_lines=3,
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

        card_content_controls.append(note_field)
        card_content_controls.append(ft.Row([ft.TextButton("Salvar anotacao", icon=ft.Icons.NOTE_ALT, on_click=_save_note)]))

        cards_column.controls.append(
            ft.Container(
                width=min(980, max(320, int(sw * 0.82))),
                content=ft.Card(
                    elevation=1,
                    content=ft.Container(
                        padding=12,
                        content=ft.Column(card_content_controls, spacing=8),
                    ),
                ),
            )
        )
        contador_text.value = f"{len(questoes)} questoes prontas"
        _update_session_meta()

    def _confirmar(_=None):
        if not questoes:
            return
        idx = estado.get("current_idx", 0)
        selected = estado["respostas"].get(idx)
        correta_idx = questoes[idx].get("correta_index", 0) if idx < len(questoes) else 0
        if selected is None or idx in estado["confirmados"]:
            return
        estado["confirmados"].add(idx)
        if not estado.get("simulado_mode"):
            tentativa_correta = selected == correta_idx
            _persist_question_flags(idx, tentativa_correta)
            status_estudo.value = "Resposta correta." if tentativa_correta else "Resposta incorreta."
        else:
            status_estudo.value = "Resposta registrada para correcao no final."
        # Mantem buffer de 2 questoes no modo continuo
        _request_quiz_buffer()
        _rebuild_cards()
        if page:
            page.update()

    def _mostrar_etapa_config():
        etapa_text.value = "Etapa 1 de 2: configure e gere"
        config_section.visible = True
        study_section.visible = False

    def _mostrar_etapa_estudo():
        if not questoes:
            _mostrar_etapa_config()
            _set_feedback_text(status_text, "Gere questoes para iniciar a resolucao.", "info")
            _refresh_status_boxes()
            return
        etapa_text.value = "Etapa 2 de 2: resolva e corrija"
        config_section.visible = False
        study_section.visible = True

    async def _prefetch_one_async():
        token = int(estado.get("generation_token", 0) or 0)
        await _ensure_quiz_buffer_async(token)

    def corrigir(_, forcar_timeout: bool = False):
        if not questoes:
            status_estudo.value = "Gere questoes antes de corrigir."
            if page:
                page.update()
            return
        if estado["corrigido"]:
            return
        nao_respondidas = [i for i in range(len(questoes)) if estado["respostas"].get(i) is None]
        if nao_respondidas and not (estado.get("simulado_mode") and forcar_timeout):
            status_estudo.value = f"Existem {len(nao_respondidas)} questoes sem resposta."
            if page:
                page.update()
            return
        acertos = 0
        total = len(questoes)
        for idx, q in enumerate(questoes):
            escolhida = estado["respostas"].get(idx)
            correta = q.get("correta_index", q.get("correta", 0))
            if escolhida == correta:
                acertos += 1
                _persist_question_flags(idx, True)
            else:
                _persist_question_flags(idx, False)
        xp = acertos * 10
        db = state["db"]
        if state.get("usuario"):
            db.registrar_resultado_quiz(state["usuario"]["id"], acertos, total, xp)
            state["usuario"]["xp"] += xp
            state["usuario"]["acertos"] += acertos
            state["usuario"]["total_questoes"] += total
            try:
                progresso = db.obter_progresso_diario(state["usuario"]["id"])
                state["usuario"]["streak_dias"] = int(progresso.get("streak_dias", state["usuario"].get("streak_dias", 0)))
            except Exception:
                pass
        taxa = (acertos / total) if total else 0.0
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
        resultado.value = f"Acertos: {acertos}/{total} | XP ganho: {xp}"
        resultado.color = CORES["sucesso"] if acertos else CORES["erro"]
        status_estudo.value = "Correcao concluida."
        resultado.update()
        estado["corrigido"] = True
        _rebuild_cards()
        if page: page.update()

    async def _gerar_quiz_async():
        if not page:
            return
        generate_button.disabled = True
        carregando.visible = True
        _set_feedback_text(status_text, "Carregando ...", "info")
        _refresh_status_boxes()
        page.update()
        try:
            try:
                dropdown_val = quiz_count_dropdown.value or "10"
                modo_continuo = dropdown_val == "cont"
                estado["modo_continuo"] = modo_continuo
                quantidade = 2 if modo_continuo else int(dropdown_val)
                quantidade = max(1, min(30, quantidade))
            except ValueError:
                quantidade = 10
                estado["modo_continuo"] = False

            if estado["modo_continuo"] and not _is_premium_active(user):
                estado["modo_continuo"] = False
                quantidade = 10
                quiz_count_dropdown.value = "10"
                _show_upgrade_dialog(page, navigate, "Modo continuo e exclusivo para planos Premium.")

            gen_profile = _generation_profile(user, "quiz")
            difficulty_key = difficulty_dropdown.value or dificuldade_padrao
            topic = (topic_field.value or "").strip()
            referencia = [line.strip() for line in (referencia_field.value or "").splitlines() if line.strip()]
            referencia = referencia + estado["upload_texts"]
            geradas = []
            session_mode = session_mode_dropdown.value or "nova"
            estado["simulado_mode"] = bool(simulado_mode_switch.value)
            estado["feedback_imediato"] = not estado["simulado_mode"]
            feedback_imediato_switch.value = estado["feedback_imediato"]
            tempo_limite_s = None
            if estado["simulado_mode"]:
                try:
                    tempo_limite_s = max(5, int(simulado_tempo_field.value or "30") * 60)
                except ValueError:
                    tempo_limite_s = 30 * 60
            estado["prova_deadline"] = None
            estado["ultimo_filtro"] = {
                "topic": topic,
                "referencia": referencia,
                "difficulty": difficulty_key,
            }
            token = _next_generation_token()
            estado["prefetch_seed"] = []
            estado["prefetch_busy"] = False
            estado["target_total"] = 0 if estado["modo_continuo"] else quantidade

            if db and user.get("id") and session_mode != "nova":
                try:
                    geradas = db.listar_questoes_usuario(user["id"], modo=session_mode, limite=max(quantidade, 20))
                except Exception as ex:
                    log_exception(ex, "main._build_quiz_body.listar_questoes_usuario")
                geradas = [q for q in (_normalize_question_for_ui(x) for x in geradas) if q]

            if gen_profile.get("delay_s", 0) > 0:
                await asyncio.sleep(float(gen_profile["delay_s"]))

            quick_start = 2 if (estado["modo_continuo"] or quantidade >= 10) else quantidade
            if geradas:
                _append_unique_questions(geradas, [])
                estado["prefetch_seed"] = [dict(q) for q in geradas[quick_start:]]
                geradas = list(geradas[:quick_start])
            if len(geradas) < quick_start:
                bloco = await _fetch_quiz_chunk_async(topic, referencia, difficulty_key, quick_start - len(geradas))
                _append_unique_questions(geradas, bloco)
            while len(geradas) < quick_start:
                geradas.append(dict(random.choice(DEFAULT_QUIZ_QUESTIONS)))

            if estado["modo_continuo"]:
                _set_feedback_text(status_text, "2 questoes prontas. Fluxo continuo ativo.", "info")
            elif quantidade >= 10:
                _set_feedback_text(status_text, f"{len(geradas)}/{quantidade} prontas. Gerando restante...", "info")
            else:
                while len(geradas) < quantidade:
                    bloco = await _fetch_quiz_chunk_async(topic, referencia, difficulty_key, quantidade - len(geradas))
                    if _append_unique_questions(geradas, bloco) <= 0:
                        break
                while len(geradas) < quantidade:
                    geradas.append(dict(random.choice(DEFAULT_QUIZ_QUESTIONS)))
                _set_feedback_text(status_text, "Pronto.", "success")
            _refresh_status_boxes()

            questoes[:] = [dict(q) for q in geradas]
            estado["current_idx"] = 0
            estado["respostas"].clear()
            estado["corrigido"] = False
            estado["confirmados"] = set()
            estado["start_time"] = time.monotonic()
            estado["prova_deadline"] = estado["start_time"] + tempo_limite_s if tempo_limite_s else None
            resultado.value = ""
            recomendacao_text.visible = False
            recomendacao_button.visible = False
            status_estudo.value = ""
            _refresh_status_boxes()
            estado["favoritas"] = set()
            estado["marcadas_erro"] = set()
            try:
                if timer_task_ref.get("task") and not timer_task_ref["task"].done():
                    pass
                timer_task_ref["task"] = page.run_task(_cronometro_task)
            except Exception:
                pass

            if db and user.get("id"):
                for idx, q in enumerate(questoes):
                    meta = q.get("_meta") or {}
                    if meta.get("favorita"):
                        estado["favoritas"].add(idx)
                    if meta.get("marcado_erro"):
                        estado["marcadas_erro"].add(idx)
                    _persist_question_flags(idx, None)

            _rebuild_cards()
            _mostrar_etapa_estudo()
            if estado.get("modo_continuo"):
                _request_quiz_buffer()
            elif quantidade >= 10 and len(questoes) < quantidade:
                page.run_task(_complete_quiz_generation_async, token, quantidade)
        except Exception as ex:
            log_exception(ex, "main._build_quiz_body._gerar_quiz_async")
            _set_feedback_text(status_text, "Falha ao gerar questoes. Tente novamente.", "error")
            _mostrar_etapa_config()
        finally:
            carregando.visible = False
            generate_button.disabled = False
            page.update()

    def _on_gerar_clique(e):
        if not page:
            return
        if generate_button.disabled:
            return
        generate_button.disabled = True
        page.update()
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
        recomendacao_text.visible = False
        recomendacao_button.visible = False
        estado["confirmados"] = set()
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

    def _quick_new_session(_):
        session_mode_dropdown.value = "nova"
        simulado_mode_switch.value = False
        estado["simulado_mode"] = False
        estado["feedback_imediato"] = True
        quiz_count_dropdown.value = "10"
        preview_count_text.value = "10"
        _set_feedback_text(status_text, "Modo treino rapido selecionado.", "info")
        if page:
            page.update()
        _on_gerar_clique(None)

    def _quick_due_reviews(_):
        session_mode_dropdown.value = "erradas"
        simulado_mode_switch.value = False
        estado["simulado_mode"] = False
        estado["feedback_imediato"] = True
        quiz_count_dropdown.value = "10"
        preview_count_text.value = "10"
        _set_feedback_text(status_text, "Modo revisao de erros selecionado.", "info")
        if page:
            page.update()
        _on_gerar_clique(None)

    def _quick_simulado(_):
        session_mode_dropdown.value = "nova"
        simulado_mode_switch.value = True
        estado["simulado_mode"] = True
        estado["feedback_imediato"] = False
        quiz_count_dropdown.value = "30"
        preview_count_text.value = "30"
        _set_feedback_text(status_text, "Modo prova selecionado.", "info")
        if page:
            page.update()
        _on_gerar_clique(None)

    # Opcoes Avancadas (ExpansionTile para limpar a tela)
    opcoes_avancadas = ft.ExpansionTile(
        title=ft.Text("Opcoes Avancadas (Sessao, Modo Prova, Filtros)", size=14, color=_color("texto", dark)),
        maintain_state=True,
        initially_expanded=False,
        controls=[
            ft.Container(
                padding=10,
                content=ft.Column([
                    ft.ResponsiveRow(
                        [
                            ft.Container(content=session_mode_dropdown, col={"sm": 12, "md": 6}),
                            ft.Container(content=simulado_mode_switch, col={"sm": 6, "md": 3}),
                            ft.Container(content=simulado_tempo_field, col={"sm": 6, "md": 3}),
                            ft.Container(
                                content=ft.Text(f"Questoes encontradas: {len(package_questions) if package_questions else 10}", size=12, weight=ft.FontWeight.BOLD),
                                col={"sm": 12, "md": 12},
                                alignment=ft.alignment.center_right,
                            ),
                        ],
                        spacing=12,
                        run_spacing=8,
                    ),
                    ft.Divider(height=1, color=_soft_border(dark, 0.1)),
                    ft.Text("Filtros Salvos", size=14, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                    ft.ResponsiveRow(
                        [
                            ft.Container(content=save_filter_name, col={"sm": 12, "md": 4}),
                            ft.Container(content=ft.ElevatedButton("Salvar filtro", icon=ft.Icons.SAVE, on_click=_save_current_filter), col={"sm": 6, "md": 2}),
                            ft.Container(content=saved_filters_dropdown, col={"sm": 12, "md": 4}),
                            ft.Container(content=ft.TextButton("Excluir", icon=ft.Icons.DELETE, on_click=_delete_selected_filter), col={"sm": 6, "md": 2}),
                        ],
                        spacing=12,
                        run_spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.END,
                    ),
                ], spacing=15)
            )
        ]
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
                                    ft.Container(content=topic_field, col={"sm": 12, "md": 12}),
                                    ft.Container(
                                        content=ft.Row(
                                            [quiz_count_dropdown, difficulty_dropdown],
                                            spacing=10,
                                            wrap=True,
                                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                        ),
                                        col={"sm": 12, "md": 12},
                                    ),
                                ],
                                spacing=12,
                                run_spacing=8,
                            ),
                            ft.Row(
                                [
                                    ft.OutlinedButton("Treino rapido", icon=ft.Icons.PLAY_ARROW, on_click=_quick_new_session),
                                    ft.OutlinedButton("Revisar erros", icon=ft.Icons.REPLAY, on_click=_quick_due_reviews),
                                    ft.OutlinedButton("Modo prova", icon=ft.Icons.TIMER, on_click=_quick_simulado),
                                ],
                                scroll=ft.ScrollMode.AUTO,
                            ),
                            opcoes_avancadas,
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
                                    generate_button,
                                    carregando,
                                    status_box,
                                ],
                                spacing=12,
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
                    ft.Row([contador_text, progresso_text, tempo_text], spacing=12),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            status_estudo_box,
            cards_column,
            ft.Container(
                padding=10,
                border_radius=8,
                bgcolor=_color("card", dark),
                content=resultado,
            ),
            ft.Row([recomendacao_text, recomendacao_button], wrap=True, spacing=10),
            ft.Row(
                [
                    ft.ElevatedButton("Corrigir", icon=ft.Icons.CHECK, on_click=corrigir),
                    ft.TextButton("Limpar respostas", icon=ft.Icons.RESTART_ALT, on_click=limpar_respostas),
                    ft.TextButton("Voltar para configuracao", icon=ft.Icons.ARROW_BACK, on_click=_voltar_config),
                    ft.TextButton("Voltar ao Inicio", icon=ft.Icons.HOME_OUTLINED, on_click=lambda _: navigate("/home")),
                ],
                wrap=True,
                spacing=10,
            ),
        ],
        spacing=12,
        expand=True,
        visible=False,
    )

    _load_saved_filters()
    _set_upload_info()
    _rebuild_cards()
    if isinstance(package_questions, list) and package_questions:
        questoes[:] = [dict(q) for q in package_questions]
        estado["current_idx"] = 0
        estado["respostas"].clear()
        estado["corrigido"] = False
        estado["start_time"] = time.monotonic()
        status_estudo.value = "Sessao carregada de pacote da Biblioteca."
        _rebuild_cards()
        _mostrar_etapa_estudo()
    elif questoes:
        _mostrar_etapa_estudo()
    else:
        _mostrar_etapa_config()

    retorno = _wrap_study_content(
        ft.Column(
            [
                _build_focus_header("Questões", "Fluxo: 1) Configure  2) Gere  3) Responda e corrija", etapa_text, dark),
                config_section,
                study_section,
            ],
            spacing=12,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
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
    user = state.get("usuario") or {}
    db = state.get("db")
    session = state.get("flashcards_session")
    if not session:
        session = {
            "flashcards": [],
            "estado": {
                "upload_texts": [],
                "upload_names": [],
                "current_idx": 0,
                "mostrar_verso": False,
                "lembrei": 0,
                "rever": 0,
                "modo_continuo": False,
                "generation_token": 0,
                "target_total": 0,
                "prefetch_seed": [],
                "prefetch_busy": False,
            },
        }
        state["flashcards_session"] = session
    flashcards = session["flashcards"]
    estado = session["estado"]
    # garante chaves
    estado.setdefault("upload_texts", [])
    estado.setdefault("upload_names", [])
    estado.setdefault("current_idx", 0)
    estado.setdefault("mostrar_verso", False)
    estado.setdefault("lembrei", 0)
    estado.setdefault("rever", 0)
    estado.setdefault("config_visivel", True)
    estado.setdefault("modo_continuo", False)
    estado.setdefault("generation_token", 0)
    estado.setdefault("target_total", 0)
    estado.setdefault("prefetch_seed", [])
    estado.setdefault("prefetch_busy", False)
    cards_column = ft.Column(
        spacing=12,
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        scroll=ft.ScrollMode.AUTO,
    )
    cards_host = ft.Container(
        content=cards_column,
        opacity=1.0,
        scale=1.0,
        animate_opacity=ft.Animation(160, ft.AnimationCurve.EASE_IN_OUT),
        animate_scale=ft.Animation(160, ft.AnimationCurve.EASE_IN_OUT),
        expand=True,
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
    # reatribui valores se ja existirem
    if estado.get("ultimo_tema"):
        tema_field.value = estado.get("ultimo_tema")
    if estado.get("ultima_referencia"):
        referencia_field.value = estado.get("ultima_referencia")
    quantidade_dropdown = ft.Dropdown(
        label="Quantidade",
        width=130 if compact else 160,
        options=[
            ft.dropdown.Option(key="3", text="3 cards"),
            ft.dropdown.Option(key="5", text="5 cards"),
            ft.dropdown.Option(key="8", text="8 cards"),
            ft.dropdown.Option(key="10", text="10 cards"),
            ft.dropdown.Option(key="cont", text="Continuo (stream)"),
        ],
        value="5",
    )
    if not _is_premium_active(user):
        quantidade_dropdown.options = [opt for opt in quantidade_dropdown.options if opt.key != "cont"]
        if quantidade_dropdown.value == "cont":
            quantidade_dropdown.value = "5"

    def _next_flash_generation_token() -> int:
        token = int(estado.get("generation_token", 0) or 0) + 1
        estado["generation_token"] = token
        return token

    def _is_flash_token_active(token: int) -> bool:
        return int(estado.get("generation_token", 0) or 0) == int(token or 0)

    def _consume_flash_prefetch_seed(limit: int) -> list:
        if limit <= 0:
            return []
        seed = list(estado.get("prefetch_seed") or [])
        if not seed:
            return []
        taken = seed[:limit]
        estado["prefetch_seed"] = seed[limit:]
        return taken

    def _append_unique_flashcards(target: list, candidates: list) -> int:
        seen = {
            str((item.get("frente") or "")).strip().lower()
            for item in target
            if isinstance(item, dict)
        }
        added = 0
        for raw in candidates or []:
            if not isinstance(raw, dict):
                continue
            frente = str(raw.get("frente") or raw.get("front") or raw.get("pergunta") or "").strip()
            verso = str(raw.get("verso") or raw.get("back") or raw.get("resposta") or "").strip()
            if not frente or not verso:
                continue
            key = frente.lower()
            if key in seen:
                continue
            seen.add(key)
            target.append({"frente": frente, "verso": verso})
            added += 1
        return added

    async def _fetch_flashcards_chunk_async(base_content: list, tema_value: str, quantidade: int) -> list:
        qtd = max(1, min(10, int(quantidade or 1)))
        bloco = []

        seed_items = _consume_flash_prefetch_seed(qtd)
        if seed_items:
            _append_unique_flashcards(bloco, seed_items)

        restante = qtd - len(bloco)
        if restante > 0:
            gen_profile = _generation_profile(user, "flashcards")
            service = _create_user_ai_service(user, force_economic=bool(gen_profile.get("force_economic")))
            if service and base_content and not _is_ai_quota_exceeded(service):
                try:
                    lote = await asyncio.to_thread(service.generate_flashcards, base_content, restante, 1)
                    _append_unique_flashcards(bloco, lote)
                except Exception as ex:
                    log_exception(ex, "main._build_flashcards_body._fetch_flashcards_chunk_async")

        base = tema_value or "Conceito"
        while len(bloco) < qtd:
            n = len(bloco) + 1
            bloco.append({"frente": f"{base} {n}", "verso": f"Resumo rapido sobre {base} {n}."})
        return bloco[:qtd]

    async def _complete_flashcards_generation_async(token: int, target_total: int):
        if not page or target_total <= 0:
            return
        while _is_flash_token_active(token) and len(flashcards) < target_total:
            restante = target_total - len(flashcards)
            lote = 10 if restante >= 10 else (5 if restante >= 5 else restante)
            bloco = await _fetch_flashcards_chunk_async(
                list(estado.get("last_base_content") or []),
                str(estado.get("last_tema") or ""),
                lote,
            )
            added = _append_unique_flashcards(flashcards, bloco)
            if added <= 0:
                break
            _set_feedback_text(status_text, f"Carregando ... {len(flashcards)}/{target_total}", "info")
            _render_flashcards()
            page.update()

        if _is_flash_token_active(token) and len(flashcards) < target_total:
            base = str(estado.get("last_tema") or "Conceito")
            while len(flashcards) < target_total:
                n = len(flashcards) + 1
                flashcards.append({"frente": f"{base} {n}", "verso": f"Resumo rapido sobre {base} {n}."})
            _render_flashcards()

        if _is_flash_token_active(token):
            _set_feedback_text(status_text, "Pronto.", "success")
            page.update()

    async def _ensure_flashcards_buffer_async(token: int):
        if not page or not estado.get("modo_continuo"):
            return
        if not _is_flash_token_active(token):
            return
        if estado.get("prefetch_busy"):
            return

        estado["prefetch_busy"] = True
        try:
            while _is_flash_token_active(token) and estado.get("modo_continuo"):
                ahead = max(0, len(flashcards) - int(estado.get("current_idx", 0)) - 1)
                need = max(0, 2 - ahead)
                if need <= 0:
                    break
                bloco = await _fetch_flashcards_chunk_async(
                    list(estado.get("last_base_content") or []),
                    str(estado.get("last_tema") or ""),
                    need,
                )
                added = _append_unique_flashcards(flashcards, bloco)
                base = str(estado.get("last_tema") or "Conceito")
                while added < need:
                    n = len(flashcards) + 1
                    flashcards.append({"frente": f"{base} {n}", "verso": f"Resumo rapido sobre {base} {n}."})
                    added += 1
                _set_feedback_text(status_text, "Fluxo continuo: 2 proximos cards prontos.", "info")
                _render_flashcards()
                page.update()
        finally:
            estado["prefetch_busy"] = False

    def _request_flashcards_buffer():
        if not page or not estado.get("modo_continuo"):
            return
        ahead = max(0, len(flashcards) - int(estado.get("current_idx", 0)) - 1)
        if ahead < 2:
            page.run_task(_ensure_flashcards_buffer_async, int(estado.get("generation_token", 0) or 0))

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

    def _mostrar_etapa_config():
        etapa_text.value = "Etapa 1 de 2: configure e gere"
        config_section.visible = True
        study_section.visible = False
        estado["config_visivel"] = True

    def _mostrar_etapa_estudo():
        etapa_text.value = "Etapa 2 de 2: revise os flashcards"
        config_section.visible = False
        study_section.visible = True
        estado["config_visivel"] = False

    def _render_flashcards():
        cards_column.controls.clear()
        screen = (_screen_width(page) if page else 1280)
        title_font = 22 if screen < 900 else (26 if screen < 1280 else 30)
        card_w = min(520, max(290, int(screen * (0.62 if compact else 0.48))))
        card_h = 430 if compact else 520
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
        card = flashcards[idx]
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
                            expand=True,
                            padding=16,
                            border_radius=12,
                            bgcolor=inner_bg,
                            content=ft.Column(
                                [
                                    ft.Container(
                                        alignment=ft.Alignment(0, 0),
                                        content=ft.Text(
                                            card.get("frente", ""),
                                            size=title_font,
                                            weight=ft.FontWeight.BOLD,
                                            color=_color("texto", dark),
                                            text_align=ft.TextAlign.CENTER,
                                        ),
                                    ),
                                    ft.Container(expand=True),
                                    ft.Container(
                                        visible=bool(estado["mostrar_verso"]),
                                        padding=12,
                                        border_radius=10,
                                        bgcolor=ft.Colors.with_opacity(0.10, CORES["primaria"]),
                                        content=ft.Column(
                                            [
                                                ft.Text("Resposta", size=11, weight=ft.FontWeight.W_600, color=CORES["primaria"]),
                                                ft.Text(card.get("verso", ""), color=_color("texto", dark), text_align=ft.TextAlign.CENTER),
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
                ),
            )
        )
        contador_flashcards.value = f"{len(flashcards)} cards"
        desempenho_text.value = f"Lembrei: {estado['lembrei']} | Rever: {estado['rever']}"

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
        estado["current_idx"] = max(0, estado["current_idx"] - 1)
        estado["mostrar_verso"] = False
        _render_flashcards()
        if page:
            page.update()

    def _next_card(_=None):
        if not flashcards:
            return
        estado["current_idx"] = min(len(flashcards) - 1, estado["current_idx"] + 1)
        estado["mostrar_verso"] = False
        _request_flashcards_buffer()
        _render_flashcards()
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
        if estado["current_idx"] < len(flashcards) - 1:
            estado["current_idx"] += 1
        estado["mostrar_verso"] = False
        status_estudo.value = "Card marcado como dominado." if lembrei else "Card marcado para revisar."
        _request_flashcards_buffer()
        _render_flashcards()
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
        await _animate_card_transition(lambda: (
            estado.__setitem__("current_idx", min(len(flashcards) - 1, estado["current_idx"] + 1)),
            estado.__setitem__("mostrar_verso", False),
        ))
        _request_flashcards_buffer()

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
        _set_feedback_text(status_text, "Carregando ...", "info")
        page.update()
        try:
            pre_profile = _generation_profile(user, "flashcards")
            try:
                qtd_value = quantidade_dropdown.value or "5"
                modo_continuo = qtd_value == "cont"
                estado["modo_continuo"] = modo_continuo
                quantidade = 2 if modo_continuo else int(qtd_value)
                quantidade = max(1, min(30, quantidade))
            except ValueError:
                quantidade = 5
                estado["modo_continuo"] = False
            if estado["modo_continuo"] and not _is_premium_active(user):
                estado["modo_continuo"] = False
                quantidade_dropdown.value = "5"
                quantidade = 5
                _show_upgrade_dialog(page, navigate, "Modo continuo de flashcards e exclusivo para planos Premium.")

            tema = (tema_field.value or "Conceito").strip()
            referencia = [line.strip() for line in (referencia_field.value or "").splitlines() if line.strip()]
            estado["ultimo_tema"] = tema
            estado["ultima_referencia"] = referencia_field.value or ""
            base_content = referencia + estado["upload_texts"]
            if not base_content and tema:
                base_content = [tema]
            estado["last_base_content"] = list(base_content)
            estado["last_tema"] = tema
            token = _next_flash_generation_token()
            estado["prefetch_seed"] = []
            estado["prefetch_busy"] = False
            estado["target_total"] = 0 if estado["modo_continuo"] else quantidade

            if pre_profile.get("delay_s", 0) > 0:
                await asyncio.sleep(float(pre_profile["delay_s"]))

            quick_start = 2 if (estado["modo_continuo"] or quantidade >= 10) else quantidade
            gerados = await _fetch_flashcards_chunk_async(base_content, tema, quick_start)
            while len(gerados) < quick_start:
                 # Se nao conseguiu gerar o minimo inicial, nao preenche com lixo.
                 # Deixa o loop de baixo tentar buscar mais ou falhar.
                 break

            flashcards[:] = list(gerados)
            estado["current_idx"] = 0
            estado["mostrar_verso"] = False
            estado["lembrei"] = 0
            estado["rever"] = 0
            _render_flashcards()
            _mostrar_etapa_estudo()

            if estado["modo_continuo"]:
                _set_feedback_text(status_text, "2 cards prontos. Fluxo continuo ativo.", "info")
                _request_flashcards_buffer()
            elif quantidade >= 10:
                _set_feedback_text(status_text, f"{len(flashcards)}/{quantidade} cards prontos. Gerando restante...", "info")
                page.run_task(_complete_flashcards_generation_async, token, quantidade)
            else:
                while len(flashcards) < quantidade:
                    bloco = await _fetch_flashcards_chunk_async(base_content, tema, quantidade - len(flashcards))
                    if _append_unique_flashcards(flashcards, bloco) <= 0:
                        break
                
                if not flashcards:
                    raise Exception("A IA não retornou nenhum flashcard válido. Verifique sua API Key ou tente outro tópico.")

                _render_flashcards()
                _set_feedback_text(status_text, "Pronto.", "success")

            status_estudo.value = status_text.value
        except Exception as ex:
            log_exception(ex, "main._build_flashcards_body._gerar_flashcards_async")
            _set_feedback_text(status_text, "Falha ao gerar flashcards. Tente novamente.", "error")
            _mostrar_etapa_config()
        finally:
            carregando.visible = False
            gerar_button.disabled = False
            page.update()

    def _on_gerar(e):
        if not page:
            return
        if gerar_button.disabled:
            return
        gerar_button.disabled = True
        page.update()
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
                            ft.Row(
                                [
                                    ft.ElevatedButton("Anexar material", icon=ft.Icons.UPLOAD_FILE, on_click=_upload_material),
                                    ft.TextButton("Limpar material", on_click=_limpar_material),
                                    upload_info,
                                ],
                                wrap=True,
                                spacing=10,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Row(
                                [
                                    gerar_button,
                                    carregando,
                                    status_text,
                                ],
                                spacing=12,
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
                    ft.Row([contador_flashcards, desempenho_text], spacing=10),
                ],
                wrap=True,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            _status_banner(status_estudo, dark),
            ft.Container(
                expand=True,
                alignment=ft.Alignment(0, -1),
                content=cards_host,
            ),
            ft.Row(
                [
                    ft.TextButton("Anterior", icon=ft.Icons.CHEVRON_LEFT, on_click=_prev_card_click),
                    ft.OutlinedButton("Mostrar resposta", icon=ft.Icons.VISIBILITY, on_click=_mostrar_resposta_click),
                    ft.ElevatedButton("Lembrei", icon=ft.Icons.CHECK_CIRCLE, on_click=_mark_lembrei),
                    ft.OutlinedButton("Rever", icon=ft.Icons.REFRESH, on_click=_mark_rever),
                    ft.TextButton("Proximo", icon=ft.Icons.CHEVRON_RIGHT, on_click=_next_card_click),
                ],
                wrap=True,
                spacing=10,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            ft.Row(
                [
                    ft.TextButton("Voltar para configuracao", icon=ft.Icons.ARROW_BACK, on_click=_voltar_config),
                    ft.TextButton("Voltar ao Inicio", icon=ft.Icons.HOME_OUTLINED, on_click=lambda _: navigate("/home")),
                ],
                wrap=True,
                spacing=10,
            ),
        ],
        spacing=12,
        expand=True,
        visible=False,
    )

    _render_flashcards()
    if flashcards:
        _mostrar_etapa_estudo()
    else:
        _mostrar_etapa_config()

    retorno = _wrap_study_content(
        ft.Column(
            [
                _build_focus_header("Flashcards", "Fluxo: 1) Configure  2) Gere  3) Revise ativamente", etapa_text, dark),
                config_section,
                study_section,
            ],
            spacing=12,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
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
        try:
            tema = (tema_field.value or "").strip() or "Tema livre"
            contexto = [f"Tema central: {tema}"] + estado["upload_texts"]
            pergunta = None
            if service:
                try:
                    pergunta = await asyncio.to_thread(service.generate_open_question, contexto, "Medio", 1)
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
                    if service:
                        _set_feedback_text(status, "IA falhou (chave/modelo). Contexto/pergunta gerados offline. Insira nova API ou troque provider.", "warning")
                    else:
                        _set_feedback_text(status, "Contexto e pergunta gerados no modo offline.", "info")
            else:
                _set_feedback_text(status, "Contexto e pergunta gerados com IA.", "success")
            estado["contexto_gerado"] = (
                pergunta.get("contexto")
                or pergunta.get("cenario")
                or f"Cenario gerado para o tema '{tema}'."
            )
            sw = _screen_width(page) if page else 1280
            pergunta_text.size = 20 if sw < 900 else (24 if sw < 1280 else 28)
            estado["pergunta"] = pergunta.get("pergunta", "")
            estado["gabarito"] = pergunta.get("resposta_esperada", "")
            contexto_gerado_text.value = f"Contexto: {estado['contexto_gerado']}"
            pergunta_text.value = estado["pergunta"]
            gabarito_text.value = f"Gabarito: {estado['gabarito']}"
            secao_texto.value = "Contexto e pergunta prontos."
            resposta_field.value = ""
            _mostrar_etapa_resposta()
        except Exception as ex:
            log_exception(ex, "main._build_open_quiz_body.gerar_async")
            _set_feedback_text(status, "Falha ao gerar contexto/pergunta. Tente novamente.", "error")
            _mostrar_etapa_geracao()
        finally:
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
                    usage = backend.consume_usage(user["id"], "open_quiz_grade", 1)
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
        try:
            feedback = None
            if service:
                try:
                    feedback = await asyncio.to_thread(
                        service.grade_open_answer,
                        estado["pergunta"],
                        resposta_field.value,
                        estado["gabarito"],
                        1,
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
            gabarito_text.value = f"Gabarito: {estado['gabarito']}\n\nFeedback: {feedback.get('feedback', '')}"
        except Exception as ex:
            log_exception(ex, "main._build_open_quiz_body.corrigir_async")
            _set_feedback_text(status, "Falha ao corrigir resposta. Tente novamente.", "error")
        finally:
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

    def _start_generate(_):
        if not page:
            return
        if loading.visible:
            return
        page.run_task(gerar, _)

    def _start_grade(_):
        if not page:
            return
        if loading.visible:
            return
        page.run_task(corrigir, _)

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
                    ft.Row(
                        [
                            ft.ElevatedButton("Anexar material", icon=ft.Icons.UPLOAD_FILE, on_click=_upload_material),
                            ft.TextButton("Limpar material", on_click=_limpar_material),
                            upload_info,
                        ],
                        wrap=True,
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            ft.ElevatedButton("Gerar contexto e pergunta", icon=ft.Icons.BOLT, on_click=_start_generate),
                            loading,
                            status,
                        ],
                        wrap=True,
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
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Container(alignment=ft.Alignment(0, 0), content=contexto_gerado_text),
            ft.Container(alignment=ft.Alignment(0, 0), content=pergunta_text),
            resposta_field,
            ft.Row(
                [
                    ft.ElevatedButton("3) Corrigir", icon=ft.Icons.CHECK, on_click=_start_grade),
                    ft.TextButton("Limpar", icon=ft.Icons.RESTART_ALT, on_click=limpar),
                    ft.TextButton("Voltar para geracao", icon=ft.Icons.ARROW_BACK, on_click=lambda _: (_mostrar_etapa_geracao(), page.update() if page else None)),
                    ft.TextButton("Voltar ao Inicio", icon=ft.Icons.HOME_OUTLINED, on_click=lambda _: navigate("/home")),
                ],
                wrap=True,
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
    user = state.get("usuario") or {}
    db = state.get("db")
    objetivo_field = ft.TextField(label="Objetivo", width=260 if compact else 360, hint_text="Ex.: Aprovacao TRT, ENEM 2026")
    data_prova_field = ft.TextField(label="Data da prova", width=150 if compact else 180, hint_text="DD/MM/AAAA")
    tempo_diario_field = ft.TextField(label="Tempo diario (min)", width=150 if compact else 180, hint_text="90")
    status_text = ft.Text("", size=12, color=_color("texto_sec", dark))
    loading = ft.ProgressRing(width=22, height=22, visible=False)
    itens_column = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)

    def _format_data_field(e):
        valor = e.control.value or ""
        apenas = "".join(ch for ch in valor if ch.isdigit())[:8]
        partes = []
        if len(apenas) >= 2:
            partes.append(apenas[:2])
        else:
            partes.append(apenas)
        if len(apenas) >= 4:
            partes.append(apenas[2:4])
        elif len(apenas) > 2:
            partes.append(apenas[2:])
        if len(apenas) > 4:
            partes.append(apenas[4:8])
        formatado = "/".join([p for p in partes if p])
        if formatado != valor:
            e.control.value = formatado
            if page:
                page.update()

    data_prova_field.on_change = _format_data_field

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
                                    ft.Text(f"{item.get('dia')} • {item.get('tema')}", weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
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
                itens = await asyncio.to_thread(service.generate_study_plan, objetivo, data_prova, tempo_diario, topicos, 1)
            if not itens:
                dias = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
                itens = [
                    {
                        "dia": d,
                        "tema": topicos[i % len(topicos)],
                        "atividade": "Questoes + revisao de erros + flashcards",
                        "duracao_min": tempo_diario,
                        "prioridade": 1 if i < 3 else 2,
                    }
                    for i, d in enumerate(dias)
                ]
            db.salvar_plano_semanal(user["id"], objetivo, data_prova, tempo_diario, itens)
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
                                ft.Row([objetivo_field, data_prova_field, tempo_diario_field], wrap=True, spacing=12),
                                ft.Row(
                                    [
                                        ft.ElevatedButton("Gerar plano", icon=ft.Icons.AUTO_AWESOME, on_click=_gerar_plano_click),
                                        loading,
                                        status_text,
                                        ft.ElevatedButton(
                                            "Estudar agora",
                                            icon=ft.Icons.PLAY_ARROW,
                                            on_click=lambda _: _start_prioritized_session(state, navigate),
                                        ),
                                    ],
                                    wrap=True,
                                    spacing=10,
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
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.BADGE, color=_color("texto_sec", dark)),
                                        ft.Container(
                                            expand=True,
                                            content=id_edit_field,
                                        ),
                                        ft.ElevatedButton(
                                            "Salvar ID",
                                            icon=ft.Icons.SAVE,
                                            on_click=_salvar_id,
                                        ),
                                    ],
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

    if backend and backend.enabled():
        try:
            backend.upsert_user(user["id"], user.get("nome", ""), user.get("email", ""))
            b = backend.get_plan(user["id"])
            sub = {
                "plan_code": b.get("plan_code", "free"),
                "premium_active": 1 if b.get("premium_active") else 0,
                "premium_until": b.get("premium_until"),
                "trial_used": 1 if b.get("plan_code") == "trial" else int(user.get("trial_used", 0) or 0),
            }
        except Exception:
            sub = db.get_subscription_status(user["id"])
    else:
        sub = db.get_subscription_status(user["id"])
    plan_code = sub.get("plan_code") or "free"
    premium_active = bool(sub.get("premium_active"))
    premium_until = sub.get("premium_until")
    trial_used = int(sub.get("trial_used") or 0)
    status_text = ft.Text("", size=12, color=_color("texto_sec", dark))

    def _refresh_status():
        if backend and backend.enabled():
            try:
                b = backend.get_plan(user["id"])
                s = {
                    "plan_code": b.get("plan_code", "free"),
                    "premium_active": 1 if b.get("premium_active") else 0,
                    "premium_until": b.get("premium_until"),
                    "trial_used": 1 if b.get("plan_code") == "trial" else int(user.get("trial_used", 0) or 0),
                }
            except Exception:
                s = db.get_subscription_status(user["id"])
        else:
            s = db.get_subscription_status(user["id"])
        state["usuario"].update(s)
        nonlocal plan_code, premium_active, premium_until, trial_used
        plan_code = s.get("plan_code") or "free"
        premium_active = bool(s.get("premium_active"))
        premium_until = s.get("premium_until")
        trial_used = int(s.get("trial_used") or 0)

    def _ativar(plano: str):
        ok = False
        msg = "Falha ao ativar plano."
        if backend and backend.enabled():
            try:
                resp = backend.activate_plan(user["id"], plano)
                ok = bool(resp.get("ok"))
                msg = resp.get("message", "Plano ativado." if ok else "Falha ao ativar plano.")
            except Exception:
                ok, msg = db.ativar_plano_premium(user["id"], plano)
        else:
            ok, msg = db.ativar_plano_premium(user["id"], plano)
        status_text.value = msg
        status_text.color = CORES["sucesso"] if ok else CORES["erro"]
        if ok:
            _refresh_status()
        if page:
            page.update()

    plano_atual = "Premium" if premium_active else ("Free (trial usado)" if trial_used else "Free")
    validade = f"Ate {premium_until}" if premium_until and premium_active else "Sem premium ativo"

    backend_status_text = "Online ativo" if (backend and backend.enabled()) else "Offline local"
    backend_status_color = CORES["acento"] if (backend and backend.enabled()) else _color("texto_sec", dark)

    return ft.Container(
        expand=True,
        bgcolor=_color("fundo", dark),
        padding=20,
        content=ft.Column(
            [
                ft.Text("Planos", size=28, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                ft.Text("Gerencie seu acesso Free/Premium.", size=14, color=_color("texto_sec", dark)),
                ft.Text(f"Sincronizacao: {backend_status_text}", size=12, color=backend_status_color),
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
                                            ft.Text(plano_atual, size=20, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
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
                                            ft.Text(validade, size=16, weight=ft.FontWeight.W_600, color=CORES["primaria"] if premium_active else _color("texto", dark)),
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
                            col={"sm": 12, "md": 6},
                            content=ft.Card(
                                elevation=1,
                                content=ft.Container(
                                    padding=12,
                                    content=ft.Column(
                                        [
                                            ft.Text("Premium 15 dias", size=16, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                            ft.Text("Velocidade e qualidade completas.", size=12, color=_color("texto_sec", dark)),
                                            ft.Text("Biblioteca: upload ilimitado por envio.", size=12, color=_color("texto_sec", dark)),
                                            ft.ElevatedButton("Ativar 15 dias", icon=ft.Icons.STAR, on_click=lambda _: _ativar("premium_15")),
                                        ],
                                        spacing=8,
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
                                            ft.Text("Premium 30 dias", size=16, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                            ft.Text("Mesmo recurso, melhor custo-beneficio.", size=12, color=_color("texto_sec", dark)),
                                            ft.Text("Biblioteca: upload ilimitado por envio.", size=12, color=_color("texto_sec", dark)),
                                            ft.ElevatedButton("Ativar 30 dias", icon=ft.Icons.WORKSPACE_PREMIUM, on_click=lambda _: _ativar("premium_30")),
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




def _build_settings_body(state, navigate, dark: bool):
    user = state.get("usuario") or {}
    db = state["db"]
    page = state.get("page")
    screen_w = _screen_width(page) if page else 1280
    compact = screen_w < 1000
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
        width=220 if compact else 260,
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
            width=260 if compact else 360,
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
        width=340 if compact else 520,
        password=True,
        can_reveal_password=True,
        value=user.get("api_key") or "",
    )
    economia_mode_switch = ft.Switch(
        label="Modo economia (prioriza modelos mais baratos/estaveis)",
        value=bool(user.get("economia_mode")),
    )
    status_api_text = ft.Text("", size=12, color=_color("texto_sec", dark))

    def _open_url(url: str):
        opened = False
        if page and hasattr(page, "launch_url"):
            try:
                page.launch_url(url)
                opened = True
            except Exception:
                opened = False
        if not opened:
            try:
                import webbrowser
                opened = webbrowser.open(url)
            except Exception:
                opened = False
        if not opened and os.name == 'nt':
            try:
                os.startfile(url)
                opened = True
            except Exception:
                pass
        if not opened and page and hasattr(page, "set_clipboard"):
            try:
                page.set_clipboard(url)
            except Exception:
                pass
        if page:
            page.snack_bar = ft.SnackBar(
                content=ft.Text(
                    "Abrindo link..." if opened else "Link copiado. Cole no navegador."
                ),
                bgcolor=CORES["info"],
                show_close_icon=True,
                duration=2000,
            )
            try:
                page.snack_bar.open = True
                page.update()
            except Exception:
                pass

    # ... (rest of buttons) ...


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
            state["usuario"]["provider"] = provider_value
            state["usuario"]["model"] = model_value
            state["usuario"]["api_key"] = api_value
            state["usuario"]["economia_mode"] = 1 if economia_mode_switch.value else 0
            log_event("settings_save", f"user_id={user_id} provider={provider_value} model={model_value}")
            if page:
                msg = "Configuracoes salvas. "
                if api_value:
                    msg += "API armazenada com sucesso."
                    status_api_text.color = CORES["sucesso"]
                else:
                    msg += "Nenhuma API informada."
                    status_api_text.color = CORES["warning"]
                status_api_text.value = msg
                page.snack_bar = ft.SnackBar(
                    content=ft.Text(msg),
                    bgcolor=CORES["sucesso"],
                    show_close_icon=True,
                )
                page.snack_bar.open = True
                page.update()
        except Exception as ex:
            log_exception(ex, "settings_save")
            if page:
                page.snack_bar = ft.SnackBar(
                    content=ft.Text("Erro ao salvar configuracoes", color="white"),
                    bgcolor=CORES["erro"],
                    show_close_icon=True,
                )
                page.snack_bar.open = True
                status_api_text.value = "Erro ao salvar. Confira a conexao ou o formato da key."
                status_api_text.color = CORES["erro"]
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
                                economia_mode_switch,
                                status_api_text,
                                ft.Container(
                                    bgcolor=ft.Colors.with_opacity(0.06, _color("texto", dark)),
                                    border_radius=10,
                                    padding=10,
                                    content=ft.Column(
                                        [
                                            ft.Text("Passo a passo rápido para pegar a API key", size=13, weight=ft.FontWeight.BOLD, color=_color("texto", dark)),
                                            ft.Text("1) Crie/entre na conta, 2) Gere a key, 3) Cole aqui.", size=12, color=_color("texto_sec", dark)),
                                            ft.Row(
                                                [
                                                    ft.ElevatedButton("Obter chave Gemini", icon=ft.Icons.LINK, on_click=lambda _: _open_url("https://aistudio.google.com/app/apikey")),
                                                    ft.ElevatedButton("Obter chave OpenAI", icon=ft.Icons.LINK, on_click=lambda _: _open_url("https://platform.openai.com/api-keys")),
                                                ],
                                                wrap=True,
                                                spacing=10,
                                            ),
                                            ft.Text("Dica: mantenha a chave salva em local seguro. Não compartilhe.", size=12, color=_color("texto_sec", dark)),
                                        ],
                                        spacing=6,
                                    ),
                                ),
                                ft.Text(
                                    "A chave e armazenada localmente e usada para gerar conteudo com IA.",
                                    size=12,
                                    color=_color("texto_sec", dark),
                                ),
                                ft.ElevatedButton("Salvar", icon=ft.Icons.SAVE, on_click=save),
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
        page.go(target)

    def go_back(_=None):
        try:
            if len(page.views) > 1:
                page.views.pop()
                top = page.views[-1]
                page.go(top.route)
            else:
                page.go("/home")
        except Exception:
            page.go("/home")

    screen_w = _screen_width(page)
    # Ajuste fino: compact agora define apenas se o sidebar sera colapsado (Rail) ou FULL.
    # Antes definia se o menu sumia (Hamburguer). Agora o menu SEMPRE existe.
    # < 900px -> Rail (Icones) | >= 900px -> Full (Icones + Texto)
    sidebar_collapsed = screen_w < 900
    
    compact = screen_w < 980
    very_compact = screen_w < 760
    show_back = route not in {"/home", "/welcome"}
    route_label = "Boas-vindas" if route == "/welcome" else next((label for r, label, _ in APP_ROUTES if r == route), "Painel")
    focus_routes = {"/quiz", "/flashcards", "/open-quiz"}
    focus_mode = route in focus_routes

    if route == "/home":
        title = "Quiz Vance"
    elif focus_mode and not very_compact:
        title = f"Modo foco: {route_label}"
    else:
        title = route_label

    user = state.get("usuario") or {}

    right_controls = [
        ft.Row(
            [
                ft.Icon(ft.Icons.DARK_MODE, size=16, color=_color("texto_sec", dark)),
                ft.Switch(value=dark, on_change=toggle_dark, scale=0.88 if compact else 0.92),
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    ]

    if not very_compact:
        user_text = f"{user.get('nome', '')}" if compact else f"{user.get('nome', '')} ({user.get('email', '')})"
        right_controls.append(ft.Text(user_text, size=11 if compact else 12, color=_color("texto_sec", dark), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS))

    # Logout button logic
    if compact:
        right_controls.append(
            ft.IconButton(icon=ft.Icons.LOGOUT, tooltip="Sair", on_click=on_logout, icon_color=CORES["erro"])
        )
    else:
        right_controls.append(
            ft.ElevatedButton("Sair", on_click=on_logout, bgcolor=CORES["erro"], color="white")
        )

    # UNIFICAÇÃO DE UI: Forçar Sidebar (Desktop-like) em vez de menu hamburguer.
    # _build_sidebar ja implementa a logica de collapsed.
    sidebar = _build_sidebar(route, navigate, dark, collapsed=sidebar_collapsed, screen_w=screen_w)

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
                            # Removemos o menu hamburguer _toggle_inline_menu
                            ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="Voltar", on_click=go_back, visible=show_back),
                            ft.Text(
                                title,
                                size=14 if very_compact else (16 if compact else 18),
                                weight=ft.FontWeight.W_700,
                                color=_color("texto", dark),
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

    content = ft.Container(
        expand=True,
        # Padding adaptativo
        padding=10 if very_compact else (12 if compact else 18),
        bgcolor=_color("fundo", dark),
        content=ft.Row(
            [
                sidebar, # AQUI ESTA A DIFERENCA: Sidebar fixa ao lado do conteudo
                ft.VerticalDivider(width=1, color=_soft_border(dark, 0.10)), # Separador visual
                ft.Container(expand=True, content=body),
            ],
            spacing=0,
            expand=True,
        ),
    )
    return ft.View(route=route, controls=[topbar, content], bgcolor=_color("fundo", dark))


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
        page.on_error = lambda e: log_exception(Exception(e.data), "flet.page.on_error")

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
        page.go(route)

    def on_login_success(usuario: dict):
        try:
            db = state.get("db")
            if db is None:
                page.snack_bar = ft.SnackBar(content=ft.Text("Carregando recursos... tente novamente em instantes."), bgcolor=CORES["warning"], show_close_icon=True)
                page.snack_bar.open = True
                page.update()
                return
            if usuario and usuario.get("id"):
                sub = None
                backend = state.get("backend")
                if backend and backend.enabled():
                    try:
                        backend.upsert_user(usuario["id"], usuario.get("nome", ""), usuario.get("email", ""))
                        b = backend.get_plan(usuario["id"])
                        sub = {
                            "plan_code": b.get("plan_code", "free"),
                            "premium_active": 1 if b.get("premium_active") else 0,
                            "premium_until": b.get("premium_until"),
                            "trial_used": 1 if b.get("plan_code") == "trial" else int(usuario.get("trial_used", 0) or 0),
                        }
                    except Exception as ex:
                        log_exception(ex, "main.on_login_success.backend_sync")
                if sub is None:
                    sub = db.get_subscription_status(int(usuario["id"]))
                usuario.update(sub)
            state["usuario"] = usuario
            state["tema_escuro"] = bool(usuario.get("tema_escuro", 0))
            state["view_cache"].clear()
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
            log_event("login_success", f"user_id={usuario.get('id')} email={usuario.get('email')}")
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
            route = page.route or "/login"

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
                    page.views[:] = [loading]
                    page.update()
                    return
                login_view = LoginView(page, db_ref, on_login_success)
                _style_form_controls(login_view, bool(state.get("tema_escuro")))
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
                else:
                    page.go("/home")
                    return

                view = _build_shell_view(page, state, route, body, on_logout, dark, toggle_dark)
                _style_form_controls(view, dark)
                # Rotas dinamicas nao devem ser cacheadas (estado interno muda)
                _no_cache_routes = {"/quiz", "/flashcards", "/open-quiz", "/settings", "/library"}
                if route not in _no_cache_routes:
                    cache[route] = view

            # Evita piscadas: sÃ³ troca se for outra instÃ¢ncia
            if page.views and page.views[-1] is view:
                log_event("route_cached", route)
                return
            page.views[:] = [view]
            page.update()
            log_event("route", route)
            log_state("state_after_route")
        except Exception as ex:
            log_exception(ex, "main.route_change")
            page.views.clear()
            page.views.append(_build_error_view(page, page.route))
            page.update()

    def view_pop(e):
        try:
            if len(page.views) <= 1:
                page.go("/home" if state["usuario"] else "/login")
                return
            page.views.pop()
            top = page.views[-1]
            page.go(top.route)
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
    # Splash e login em blocos separados:
    # 1) mostra splash (sem carga pesada de runtime)
    # 2) apos 2.8s vai para /login e so entao inicia runtime na rota
    is_android = bool(os.getenv("ANDROID_DATA"))
    splash_view, logo_box, tagline = _build_splash(page, navigate, state["tema_escuro"])
    page.views[:] = [splash_view]
    page.update()

    async def run_splash():
        # Android: splash estatica por 2.8s para reduzir risco de black screen em transicao animada.
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
            await asyncio.sleep(2.8)
            page.go("/login")
            page.update()
            return

        # Desktop: fade + micro zoom
        logo_box.opacity = 1
        logo_box.width = 200
        logo_box.height = 200
        tagline.opacity = 1
        page.update()
        await asyncio.sleep(2.55)  # tempo principal de exibicao
        # fade out curto
        if splash_view.controls and hasattr(splash_view.controls[0], "content"):
            splash_root = splash_view.controls[0].content
            splash_root.opacity = 0
            page.update()
        await asyncio.sleep(0.25)  # total ~2.8s
        page.go("/login")
        page.update()
    try:
        page.run_task(run_splash)
    except Exception as ex:
        # Fallback para versoes de Flet com comportamento diferente em run_task.
        log_exception(ex, "main.run_splash")
        page.go("/login")






