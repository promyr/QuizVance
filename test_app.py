# -*- coding: utf-8 -*-
"""
Teste simples da aplicacao
"""

from config import CORES


def test_main_smoke():
    """Smoke: paleta basica carregou."""
    assert "fundo" in CORES and "card" in CORES
