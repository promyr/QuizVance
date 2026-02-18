# -*- coding: utf-8 -*-
"""
LoginView - versao estavel para Flet 0.80.x
"""

import threading
import os
import flet as ft

from config import CORES, GOOGLE_OAUTH
from core.auth_service import authenticate_with_google
from core.error_monitor import log_exception


class LoginView(ft.View):
    def __init__(self, page, database, on_login_success):
        super().__init__(route="/login")
        self._page = page
        self.db = database
        self.on_login_success = on_login_success
        self.tema_escuro = page.theme_mode == ft.ThemeMode.DARK
        self.modo_atual = "login"
        self.autenticando_google = False
        self.google_login_enabled = bool(GOOGLE_OAUTH.get("enabled", False))
        self._prev_keyboard_handler = getattr(self._page, "on_keyboard_event", None)

        self._criar_componentes()
        self._construir_interface()
        self._page.on_keyboard_event = self._on_keyboard_event

    def _criar_componentes(self):
        # Login
        self.email_login = ft.TextField(
            label="ID",
            hint_text="seu_id",
            width=360,
            prefix_icon=ft.Icons.PERSON,
            autofocus=True,
        )
        self.senha_login = ft.TextField(
            label="Senha",
            password=True,
            can_reveal_password=True,
            width=360,
            prefix_icon=ft.Icons.LOCK,
        )

        # Cadastro
        self.nome_cad = ft.TextField(label="Nome completo", width=360, prefix_icon=ft.Icons.PERSON)
        self.email_cad = ft.TextField(label="ID", width=360, prefix_icon=ft.Icons.PERSON)
        self.senha_cad = ft.TextField(
            label="Senha",
            password=True,
            can_reveal_password=True,
            width=360,
            prefix_icon=ft.Icons.LOCK,
        )
        self.idade_cad = ft.TextField(
            label="Data de nascimento",
            hint_text="DD/MM/AAAA",
            width=360,
            keyboard_type=ft.KeyboardType.DATETIME,
            prefix_icon=ft.Icons.CAKE,
        )
        self.idade_cad.on_change = self._on_data_nascimento_change

        self.email_login.on_submit = self._submit_login_id
        self.senha_login.on_submit = self._submit_login
        self.nome_cad.on_submit = self._submit_cadastro_nome
        self.email_cad.on_submit = self._submit_cadastro_email
        self.senha_cad.on_submit = self._submit_cadastro_senha
        self.idade_cad.on_submit = self._submit_cadastro

        self.loading = ft.Column(
            controls=[
                ft.ProgressRing(width=36, height=36),
                ft.Text("Autenticando com Google...", size=13),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
            visible=False,
        )
        self.login_feedback = ft.Text("", visible=False, size=12, text_align=ft.TextAlign.CENTER)

    def _construir_interface(self):
        bg_color = CORES["fundo_escuro"] if self.tema_escuro else CORES["fundo"]
        card_color = CORES["card_escuro"] if self.tema_escuro else CORES["card"]
        text_color = CORES["texto_escuro"] if self.tema_escuro else CORES["texto"]
        muted_color = CORES["texto_sec_escuro"] if self.tema_escuro else CORES["texto_sec"]
        border_color = "#374151" if self.tema_escuro else "#E5E7EB"

        # Responsivo real para desktop/mobile
        screen_w = float(getattr(self._page, "width", None) or getattr(self._page, "window_width", 1024) or 1024)
        screen_h = float(getattr(self._page, "height", None) or getattr(self._page, "window_height", 820) or 820)
        compact = screen_w < 860
        mobile = screen_w < 520
        short_height = screen_h < 760

        content_w = min(560, screen_w - (16 if mobile else (24 if compact else 120)))
        logo_w = min(520 if compact else 760, screen_w - (24 if mobile else (40 if compact else 160)))

        if mobile:
            logo_h = 60 if short_height else 72
        elif short_height:
            logo_h = 86
        elif compact:
            logo_h = 104
        else:
            logo_h = 240

        root_padding = 6 if mobile else (10 if compact else 24)
        field_width = max(240 if mobile else 280, content_w - (18 if mobile else (24 if compact else 40)))

        self.container_login = ft.Column(
            controls=[
                ft.Text("Bem-vindo de volta!", size=22 if mobile else (30 if compact else 34), weight=ft.FontWeight.BOLD, color=text_color),
                ft.Text("Entre para continuar", size=13 if mobile else 14, color=muted_color),
                ft.Container(height=2 if mobile else 6),
                ft.ElevatedButton(
                    "Continuar com Google" if self.google_login_enabled else "Continuar com Google (em breve)",
                    icon=ft.Icons.ACCOUNT_CIRCLE,
                    width=field_width,
                    height=40 if mobile else 42,
                    on_click=self._login_google,
                    disabled=not self.google_login_enabled,
                    style=ft.ButtonStyle(
                        bgcolor=card_color,
                        color=text_color,
                        shape=ft.RoundedRectangleBorder(radius=12),
                    ),
                ),
                ft.Text("ou acesso manual", size=10 if mobile else 11, color=muted_color),
                self.email_login,
                self.senha_login,
                self.login_feedback,
                ft.ElevatedButton(
                    "Entrar",
                    icon=ft.Icons.LOGIN,
                    width=field_width,
                    height=42 if mobile else 44,
                    on_click=self._acao_login,
                    style=ft.ButtonStyle(
                        bgcolor=CORES["primaria"],
                        color="white",
                        shape=ft.RoundedRectangleBorder(radius=12),
                    ),
                ),
                ft.Row(
                    controls=[
                        ft.Text("Sem conta?", color=muted_color),
                        ft.TextButton("Cadastre-se", on_click=self._trocar_para_cadastro),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=4,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6 if compact else 8,
            visible=True,
        )

        self.container_cadastro = ft.Column(
            controls=[
                ft.Text("Criar conta", size=22 if mobile else (30 if compact else 34), weight=ft.FontWeight.BOLD, color=text_color),
                ft.Text("Comece sua jornada", size=12 if mobile else 13, color=muted_color),
                ft.Container(height=2 if mobile else 6),
                ft.ElevatedButton(
                    "Cadastrar com Google" if self.google_login_enabled else "Cadastrar com Google (em breve)",
                    icon=ft.Icons.ACCOUNT_CIRCLE,
                    width=field_width,
                    height=40 if mobile else 42,
                    on_click=self._login_google,
                    disabled=not self.google_login_enabled,
                    style=ft.ButtonStyle(
                        bgcolor=card_color,
                        color=text_color,
                        shape=ft.RoundedRectangleBorder(radius=12),
                    ),
                ),
                ft.Text("ou preencha seus dados", size=10 if mobile else 11, color=muted_color),
                self.nome_cad,
                self.email_cad,
                self.senha_cad,
                self.idade_cad,
                ft.ElevatedButton(
                    "Criar conta",
                    icon=ft.Icons.PERSON_ADD,
                    width=field_width,
                    height=42 if mobile else 44,
                    on_click=self._acao_cadastro,
                    style=ft.ButtonStyle(
                        bgcolor=CORES["primaria"],
                        color="white",
                        shape=ft.RoundedRectangleBorder(radius=12),
                    ),
                ),
                ft.Row(
                    controls=[
                        ft.Text("Ja tem conta", color=muted_color),
                        ft.TextButton("Fazer login", on_click=self._trocar_para_login),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6 if compact else 8,
            visible=False,
        )

        for field in [
            self.email_login,
            self.senha_login,
            self.nome_cad,
            self.email_cad,
            self.senha_cad,
            self.idade_cad,
        ]:
            field.width = field_width

        self.botao_modo_login = ft.TextButton("Entrar", on_click=self._trocar_para_login)
        self.botao_modo_cadastro = ft.TextButton("Criar conta", on_click=self._trocar_para_cadastro)

        hero_logo = ft.Container(
            width=logo_w,
            height=logo_h,
            alignment=ft.Alignment(0, 0),
            content=ft.Image(
                src=os.path.join("assets", "logo_quizvance.png"),
                width=logo_w,
                height=logo_h,
                fit="contain",
            ),
        )

        auth_card = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[self.botao_modo_login, self.botao_modo_cadastro],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=14,
                    ),
                    ft.Container(height=2 if mobile else 6),
                    self.container_login,
                    self.container_cadastro,
                    self.loading,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8 if compact else 10,
            ),
            width=content_w,
            padding=14 if mobile else (18 if compact else 24),
            border_radius=16 if mobile else (18 if compact else 22),
            bgcolor=card_color,
            border=ft.Border.all(1, border_color),
            shadow=ft.BoxShadow(blur_radius=32, spread_radius=1, color=ft.Colors.with_opacity(0.16, "#000000")),
        )

        self.botao_modo_login.style = ft.ButtonStyle(
            bgcolor=CORES["primaria"] if self.modo_atual == "login" else "transparent",
            color="white" if self.modo_atual == "login" else muted_color,
            shape=ft.RoundedRectangleBorder(radius=999),
            padding=ft.Padding(14 if compact else 18, 8 if compact else 10, 14 if compact else 18, 8 if compact else 10),
        )
        self.botao_modo_cadastro.style = ft.ButtonStyle(
            bgcolor=CORES["primaria"] if self.modo_atual == "cadastro" else "transparent",
            color="white" if self.modo_atual == "cadastro" else muted_color,
            shape=ft.RoundedRectangleBorder(radius=999),
            padding=ft.Padding(14 if compact else 18, 8 if compact else 10, 14 if compact else 18, 8 if compact else 10),
        )

        layout = ft.Column(
            controls=[hero_logo, auth_card],
            alignment=ft.MainAxisAlignment.START if compact else ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0 if compact else 12,
        )

        root = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=layout,
                        alignment=ft.Alignment(0, 0),
                        padding=ft.padding.only(bottom=2 if compact else 12),
                    )
                ],
                spacing=0,
                expand=True,
                scroll=ft.ScrollMode.AUTO,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=root_padding, vertical=2 if compact else root_padding),
            expand=True,
            bgcolor="#EEF2FF" if not self.tema_escuro else bg_color,
        )

        self.controls.clear()
        self.controls.append(root)
        self._aplicar_estilo_modo()

    def _aplicar_estilo_modo(self):
        ativo = ft.ButtonStyle(bgcolor=CORES["primaria"], color="white")
        inativo = ft.ButtonStyle(bgcolor="transparent", color=CORES["texto_sec"])
        if self.modo_atual == "cadastro":
            self.container_login.visible = False
            self.container_cadastro.visible = True
            self.botao_modo_login.style = inativo
            self.botao_modo_cadastro.style = ativo
        else:
            self.container_login.visible = True
            self.container_cadastro.visible = False
            self.botao_modo_login.style = ativo
            self.botao_modo_cadastro.style = inativo

    def _trocar_para_cadastro(self, e):
        self.modo_atual = "cadastro"
        self._aplicar_estilo_modo()
        self.update()

    def _trocar_para_login(self, e):
        self.modo_atual = "login"
        self._aplicar_estilo_modo()
        self.update()

    def _acao_login(self, e):
        try:
            email = (self.email_login.value or "").strip()
            senha = self.senha_login.value or ""
            self.login_feedback.visible = False
            self.login_feedback.value = ""
            self.login_feedback.update()

            if not email or not senha:
                self._set_login_feedback("Preencha ID e senha para entrar.", "warning")
                self._mostrar_toast("Preencha todos os campos", "warning")
                return

            usuario = self.db.fazer_login(email, senha)
            if usuario:
                self._set_login_feedback("Login realizado. Entrando...", "sucesso")
                self.on_login_success(usuario)
            else:
                if hasattr(self.db, "contar_usuarios") and self.db.contar_usuarios() == 0:
                    self._set_login_feedback("Nenhuma conta cadastrada. Crie sua conta primeiro.", "warning")
                    self._mostrar_toast("Nenhuma conta cadastrada. Use 'Cadastre-se' primeiro.", "warning")
                else:
                    self._set_login_feedback("ID ou senha incorretos.", "erro")
                    self._mostrar_toast("ID ou senha incorretos", "erro")
                    self._page.update()
        except Exception as ex:
            log_exception(ex, "login_view._acao_login")
            self._set_login_feedback("Erro interno ao tentar login.", "erro")
            self._mostrar_toast("Erro interno no login. Veja os logs do aplicativo", "erro")

    def _submit_login(self, e):
        self._acao_login(e)

    def _submit_login_id(self, e):
        self._focar_campo(self.senha_login)

    def _acao_cadastro(self, e):
        try:
            nome = (self.nome_cad.value or "").strip()
            identificador = (self.email_cad.value or "").strip()
            senha = self.senha_cad.value or ""
            data_nascimento = (self.idade_cad.value or "").strip()

            if not all([nome, identificador, senha, data_nascimento]):
                self._mostrar_toast("Preencha todos os campos", "warning")
                return

            try:
                import datetime
                nascimento = datetime.datetime.strptime(data_nascimento, "%d/%m/%Y").date()
                hoje = datetime.date.today()
                idade = hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
                if idade < 13:
                    self._mostrar_toast("Idade minima: 13 anos", "warning")
                    return
            except ValueError:
                self._mostrar_toast("Data invalida. Use DD/MM/AAAA", "warning")
                return

            if len(senha) < 6:
                self._mostrar_toast("Senha deve ter no minimo 6 caracteres", "warning")
                return

            sucesso, msg = self.db.criar_conta(nome, identificador, senha, data_nascimento)
            if sucesso:
                self._mostrar_toast("Conta criada com sucesso. Clique em 'Fazer login' para continuar.", "sucesso")
                self.senha_cad.value = ""
                self.idade_cad.value = ""
                self._trocar_para_login(None)
                self.login_feedback.value = "Conta criada! Use seu ID e senha para entrar."
                self.login_feedback.color = CORES["sucesso"]
                self.login_feedback.visible = True
                self.update()
            else:
                self._mostrar_toast(msg, "erro")
        except Exception as ex:
            log_exception(ex, "login_view._acao_cadastro")
            self._mostrar_toast("Erro interno no cadastro. Veja os logs do aplicativo", "erro")

    def _submit_cadastro(self, e):
        self._acao_cadastro(e)

    def _submit_cadastro_nome(self, e):
        self._focar_campo(self.email_cad)

    def _submit_cadastro_email(self, e):
        self._focar_campo(self.senha_cad)

    def _submit_cadastro_senha(self, e):
        self._focar_campo(self.idade_cad)

    def _focar_campo(self, campo):
        try:
            self._page.run_task(campo.focus)
        except Exception:
            pass

    def _on_data_nascimento_change(self, e):
        valor = e.control.value or ""
        apenas_numeros = "".join(ch for ch in valor if ch.isdigit())[:8]
        partes = []
        if len(apenas_numeros) >= 2:
            partes.append(apenas_numeros[:2])
        else:
            partes.append(apenas_numeros)
        if len(apenas_numeros) >= 4:
            partes.append(apenas_numeros[2:4])
        elif len(apenas_numeros) > 2:
            partes.append(apenas_numeros[2:])
        if len(apenas_numeros) > 4:
            partes.append(apenas_numeros[4:8])
        formatado = "/".join([p for p in partes if p])
        if formatado != valor:
            self.idade_cad.value = formatado
            self.idade_cad.update()

    def _on_keyboard_event(self, e: ft.KeyboardEvent):
        # Fluxo de autenticacao exige acao explicita por botao.
        if callable(self._prev_keyboard_handler):
            self._prev_keyboard_handler(e)

    def _login_google(self, e):
        if not self.google_login_enabled:
            self._mostrar_toast("Login com Google temporariamente desativado.", "info")
            return

        if self.autenticando_google:
            return

        # Validacao rapida para evitar erro 401 com client_id placeholder
        client_id = GOOGLE_OAUTH.get("client_id", "")
        if not client_id or "YOUR_CLIENT_ID" in client_id or "apps.googleusercontent.com" not in client_id:
            self._mostrar_toast("Configure um client_id OAuth valido em config.py antes de usar Google Login.", "warning")
            log_exception(Exception("google_oauth_placeholder"), "login_view._login_google")
            return

        self.autenticando_google = True
        self.container_login.visible = False
        self.container_cadastro.visible = False
        self.loading.visible = True
        self.update()

        def auth_thread():
            try:
                result = authenticate_with_google(
                    GOOGLE_OAUTH["client_id"],
                    GOOGLE_OAUTH["redirect_uri"],
                    GOOGLE_OAUTH["scopes"],
                )
                if result:
                    user_info = result["user_info"]
                    usuario = self.db.fazer_login_oauth(
                        email=user_info["email"],
                        nome=user_info.get("name", ""),
                        google_id=user_info.get("id", ""),
                        avatar_url=user_info.get("picture", ""),
                    )
                    if usuario:
                        self._page.run_thread(lambda: self.on_login_success(usuario))
                    else:
                        self._page.run_thread(lambda: self._mostrar_toast("Erro ao autenticar com Google", "erro"))
                else:
                    self._page.run_thread(lambda: self._mostrar_toast("Autenticacao cancelada", "warning"))
            except Exception as ex:
                print(f"[LOGIN] Erro Google OAuth: {ex}")
                log_exception(ex, "login_view._login_google")
                self._page.run_thread(lambda: self._mostrar_toast("Erro na autenticacao Google", "erro"))
            finally:
                self.autenticando_google = False
                self.loading.visible = False
                if self.modo_atual == "login":
                    self.container_login.visible = True
                else:
                    self.container_cadastro.visible = True
                self._page.run_thread(lambda: self.update())

        threading.Thread(target=auth_thread, daemon=True).start()

    def _set_login_feedback(self, msg: str, tipo: str):
        cores = {
            "sucesso": CORES["sucesso"],
            "erro": CORES["erro"],
            "warning": CORES["warning"],
            "info": CORES["info"],
        }
        self.login_feedback.value = msg
        self.login_feedback.color = cores.get(tipo, CORES["info"])
        self.login_feedback.visible = True
        self.update()

    def _mostrar_toast(self, msg: str, tipo: str):
        cores = {
            "sucesso": CORES["sucesso"],
            "erro": CORES["erro"],
            "warning": CORES["warning"],
            "info": CORES["info"],
        }
        sb = ft.SnackBar(
            content=ft.Text(msg, color="white"),
            bgcolor=cores.get(tipo, CORES["info"]),
            show_close_icon=True,
            duration=2500,
        )
        # Compatibilidade entre versoes de Flet.
        try:
            self._page.show_snack_bar(sb)
            return
        except Exception:
            pass
        try:
            self._page.open(sb)
            return
        except Exception:
            pass
        self._page.snack_bar = sb
        self._page.snack_bar.open = True
        self._page.update()








