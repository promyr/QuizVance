#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para corrigir imports automaticamente
Execute: python fix_imports.py
"""

import os
import re


def fix_file(filepath):
    """Corrige imports em um arquivo"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"âŒ Erro ao ler {filepath}: {e}")
        return
    
    original = content
    
    # Corrigir imports
    replacements = [
        (r'from ui.components_v2 import', 'from ui.components_v2 import'),
        (r'from core.auth_service import', 'from core.auth_service import'),
        (r'from core.database_v2 import', 'from core.database_v2 import'),
        (r'from core.ai_service_v2 import', 'from core.ai_service_v2 import'),
        (r'from core.sounds import', 'from core.sounds import'),
    ]
    
    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content)
    
    if content != original:
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"âœ… Corrigido: {filepath}")
            return True
        except Exception as e:
            print(f"âŒ Erro ao salvar {filepath}: {e}")
            return False
    else:
        print(f"â­ï¸  OK: {filepath}")
        return False


def main():
    """Executa correÃ§Ã£o em todos os arquivos"""
    print("=" * 60)
    print("ðŸ”§ CORRETOR DE IMPORTS - QuizVance V2.0")
    print("=" * 60)
    print()
    
    fixed_count = 0
    total_count = 0
    
    for root, dirs, files in os.walk('.'):
        # Ignorar diretÃ³rios
        dirs[:] = [d for d in dirs if d not in [
            '__pycache__', 'venv', 'env', '.git', 
            'node_modules', '.vscode', '.idea'
        ]]
        
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                total_count += 1
                
                if fix_file(filepath):
                    fixed_count += 1
    
    print()
    print("=" * 60)
    print("RESUMO")
    print("=" * 60)
    print(f"Arquivos verificados: {total_count}")
    print(f"Arquivos corrigidos: {fixed_count}")
    print(f"Arquivos OK: {total_count - fixed_count}")
    print()
    
    if fixed_count > 0:
        print("âœ… CorreÃ§Ãµes aplicadas com sucesso!")
        print("   Execute novamente: python run.py")
    else:
        print("âœ… Todos os imports estÃ£o corretos!")
    print()


if __name__ == '__main__':
    main()

