# -*- coding: utf-8 -*-
"""
Suite de Testes Automatizados - Quiz Vance
"""

import unittest
import json
from core.ai_service_v2 import GeminiProvider, OpenAIProvider, AIService, create_ai_provider
from config import CORES, AI_PROVIDERS


class TestAIService(unittest.TestCase):
    """Testes do serviÃ§o de IA"""
    
    def setUp(self):
        """Setup antes de cada teste"""
        # Nota: VocÃª precisa definir estas variÃ¡veis de ambiente ou usar suas chaves
        self.gemini_key = "YOUR_GEMINI_KEY"
        self.openai_key = "YOUR_OPENAI_KEY"
    
    def test_create_gemini_provider(self):
        """Testa criaÃ§Ã£o de provider Gemini"""
        try:
            provider = create_ai_provider("gemini", self.gemini_key)
            self.assertIsInstance(provider, GeminiProvider)
            print("âœ… Gemini provider criado com sucesso")
        except ImportError:
            print("âš ï¸  google-generativeai nÃ£o instalado, pulando teste")
    
    def test_create_openai_provider(self):
        """Testa criaÃ§Ã£o de provider OpenAI"""
        try:
            provider = create_ai_provider("openai", self.openai_key)
            self.assertIsInstance(provider, OpenAIProvider)
            print("âœ… OpenAI provider criado com sucesso")
        except ImportError:
            print("âš ï¸  openai nÃ£o instalado, pulando teste")
    
    def test_extract_json_object(self):
        """Testa extraÃ§Ã£o de JSON de texto"""
        provider = create_ai_provider("gemini", "fake_key")
        
        # Teste 1: JSON limpo
        text1 = '{"pergunta": "Test?", "opcoes": ["A", "B"], "correta_index": 0}'
        result1 = provider.extract_json_object(text1)
        self.assertIsNotNone(result1)
        self.assertEqual(result1["pergunta"], "Test?")
        print("âœ… ExtraÃ§Ã£o de JSON limpo funcionou")
        
        # Teste 2: JSON com markdown
        text2 = '''
        ```json
        {"pergunta": "Test?", "opcoes": ["A", "B"], "correta_index": 0}
        ```
        '''
        result2 = provider.extract_json_object(text2)
        self.assertIsNotNone(result2)
        self.assertEqual(result2["pergunta"], "Test?")
        print("âœ… ExtraÃ§Ã£o de JSON com markdown funcionou")
        
        # Teste 3: JSON com texto antes/depois
        text3 = '''
        Aqui estÃ¡ o JSON:
        {"pergunta": "Test?", "opcoes": ["A", "B"], "correta_index": 0}
        Espero que ajude!
        '''
        result3 = provider.extract_json_object(text3)
        self.assertIsNotNone(result3)
        self.assertEqual(result3["pergunta"], "Test?")
        print("âœ… ExtraÃ§Ã£o de JSON com texto extra funcionou")
    
    def test_normalize_quiz(self):
        """Testa normalizaÃ§Ã£o de quiz"""
        provider = create_ai_provider("gemini", "fake_key")
        service = AIService(provider)
        
        # Teste 1: Formato padrÃ£o
        data1 = {
            "pergunta": "Quanto Ã© 2+2?",
            "opcoes": ["1", "2", "3", "4"],
            "correta_index": 3,
            "explicacao": "2+2 = 4"
        }
        result1 = service._normalize_quiz(data1)
        self.assertIsNotNone(result1)
        self.assertEqual(result1["correta_index"], 3)
        print("âœ… NormalizaÃ§Ã£o formato padrÃ£o funcionou")
        
        # Teste 2: Formato alternativo
        data2 = {
            "question": "Quanto Ã© 2+2?",
            "options": ["1", "2", "3", "4"],
            "answer": "D",
            "explanation": "2+2 = 4"
        }
        result2 = service._normalize_quiz(data2)
        self.assertIsNotNone(result2)
        self.assertEqual(result2["correta_index"], 3)
        print("âœ… NormalizaÃ§Ã£o formato alternativo funcionou")
        
        # Teste 3: OpÃ§Ãµes como objetos
        data3 = {
            "pergunta": "Quanto Ã© 2+2?",
            "opcoes": [
                {"texto": "1"},
                {"texto": "2"},
                {"texto": "3"},
                {"texto": "4"}
            ],
            "correta_index": 3
        }
        result3 = service._normalize_quiz(data3)
        self.assertIsNotNone(result3)
        self.assertEqual(len(result3["opcoes"]), 4)
        print("âœ… NormalizaÃ§Ã£o opÃ§Ãµes como objetos funcionou")


class TestConfig(unittest.TestCase):
    """Testes de configuraÃ§Ã£o"""
    
    def test_cores_defined(self):
        """Testa se todas as cores estÃ£o definidas"""
        cores_necessarias = [
            "primaria", "acento", "fundo", "card", "texto",
            "erro", "sucesso", "warning", "info"
        ]
        
        for cor in cores_necessarias:
            self.assertIn(cor, CORES)
            self.assertIsInstance(CORES[cor], str)
            self.assertTrue(CORES[cor].startswith("#"))
        
        print("âœ… Todas as cores estÃ£o definidas")
    
    def test_ai_providers_config(self):
        """Testa configuraÃ§Ã£o de providers de IA"""
        self.assertIn("gemini", AI_PROVIDERS)
        self.assertIn("openai", AI_PROVIDERS)
        
        for provider_name, config in AI_PROVIDERS.items():
            self.assertIn("name", config)
            self.assertIn("models", config)
            self.assertIn("default_model", config)
            self.assertIsInstance(config["models"], list)
            self.assertGreater(len(config["models"]), 0)
        
        print("âœ… ConfiguraÃ§Ã£o de AI providers vÃ¡lida")


class TestComponents(unittest.TestCase):
    """Testes de componentes UI"""
    
    def test_get_cor(self):
        """Testa funÃ§Ã£o get_cor"""
        from ui.components_v2 import get_cor
        
        # Tema claro
        cor_clara = get_cor("primaria", tema_escuro=False)
        self.assertEqual(cor_clara, CORES["primaria"])
        
        # Tema escuro
        cor_escura = get_cor("fundo", tema_escuro=True)
        self.assertEqual(cor_escura, CORES["fundo_escuro"])
        
        print("âœ… FunÃ§Ã£o get_cor funcionando")


class TestDatabase(unittest.TestCase):
    """Testes de banco de dados"""
    
    def setUp(self):
        """Setup do banco de teste"""
        import os
        # Criar banco de teste
        self.test_db = "test_simulador.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
    
    def tearDown(self):
        """Cleanup apÃ³s teste"""
        import os
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
    
    def test_database_creation(self):
        """Testa criaÃ§Ã£o e tabelas essenciais usando database_v2.py"""
        from core.database_v2 import Database
        db = Database(db_path=self.test_db)
        db.iniciar_banco()
        
        import sqlite3
        conn = sqlite3.connect(self.test_db)
        cur = conn.cursor()
        # checar tabelas principais
        tabelas = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        esperadas = {
            "usuarios", "user_ai_config", "oauth_users",
            "historico_xp", "questoes_erros", "conquistas",
            "usuario_conquistas", "estudo_tempo_diario",
            "biblioteca_pdfs", "banco_questoes"
        }
        faltando = esperadas - tabelas
        self.assertFalse(faltando, f"Tabelas faltando: {faltando}")
        conn.close()
        print("âœ… Banco criado com tabelas essenciais")


def run_all_tests():
    """Executa todos os testes"""
    print("=" * 60)
    print("EXECUTANDO TESTES - Quiz Vance V2")
    print("=" * 60)
    print()
    
    # Criar suite de testes
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Adicionar testes
    suite.addTests(loader.loadTestsFromTestCase(TestAIService))
    suite.addTests(loader.loadTestsFromTestCase(TestConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestComponents))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabase))
    
    # Executar
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Resumo
    print()
    print("=" * 60)
    print("RESUMO")
    print("=" * 60)
    print(f"Testes executados: {result.testsRun}")
    print(f"âœ… Sucessos: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"âŒ Falhas: {len(result.failures)}")
    print(f"âš ï¸  Erros: {len(result.errors)}")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)



