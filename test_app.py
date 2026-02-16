# -*- coding: utf-8 -*-
"""
Teste simples da aplicacao
"""

import flet as ft
from config import CORES

def test_main(page: ft.Page):
    """Teste simples"""
    page.title = "QuizVance V2.0 - TESTE"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = CORES["fundo"]
    page.padding = 20
    
    # Teste 1: Texto simples
    page.add(
        ft.Text("[OK] Aplicacao carregada com sucesso!", size=24, weight="bold"),
        ft.Divider(),
        ft.Text("Tela vazia = problema de renderizacao"),
        ft.Text("Se voce ve isto, e um teste bem-sucedido!"),
        ft.Divider(),
        ft.ElevatedButton("Botao de Teste", on_click=lambda e: print("Clicado!")),
    )

if __name__ == "__main__":
    ft.run(test_main)

