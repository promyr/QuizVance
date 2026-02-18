<div align="center">
  <img src="assets/logo_quizvance.png" alt="Logo Quiz Vance" width="200" />
  
  <h1>Quiz Vance App</h1>
  
  <p>Estudo assistido por IA · Questões · Flashcards · Planos Semanais · Android & Desktop</p>

  <img src="https://img.shields.io/badge/Python-3.14-blue?logo=python&logoColor=white" alt="Python 3.14">
  <img src="https://img.shields.io/badge/Flet-0.80.x-00E6F8?logo=flutter&logoColor=white" alt="Flet">
  <img src="https://img.shields.io/badge/Plataforma-Android%20%7C%20Desktop-lightgrey" alt="Plataformas">

  <br><br>

  <a href="#-destaques">Destaques</a> ·
  <a href="#-stack-técnica">Stack</a> ·
  <a href="#-setup-rápido">Setup</a> ·
  <a href="#-build-android">Build Android</a> ·
  <a href="#-configuração-de-ia">Configurar IA</a> ·
  <a href="#-roadmap">Roadmap</a>
</div>

---

## ✨ Destaques

- **Questões Objetivas:** Resoluções com feedback imediato e modo prova com cronômetro integrado.
- **Flashcards com IA:** Geração inteligente de cards, revisão ativa e registro de progresso contínuo.
- **Upload de Arquivos:** Suporte nativo a PDF, TXT e MD para a criação de quizzes personalizados e alimentação de uma biblioteca local.
- **Gestão de Estudos:** Plano semanal guiado por IA, painel de estatísticas e temas (claro/escuro) persistentes.
- **Pronto para Produção:** Build Android facilitado via `flet build apk` com script de automação incluso.

## 🧩 Stack Técnica

- **Framework UI:** Flet 0.80.x (Flutter *under the hood*).
- **Linguagem:** Python 3.14.
- **Inteligência Artificial:** Google Gemini (`google-genai`) e OpenAI (`openai`), com sistema de *fallback* econômico.
- **Banco de Dados Local:** SQLite (gerenciado via `core/database_v2.py`).

## 📂 Estrutura Principal

- `main_v2.py`: Arquivo shell, mapeamento de rotas, views e regras de negócio.
- `ui/views/login_view_v2.py`: Fluxos de autenticação e onboarding.
- `core/ai_service_v2.py`: Integração com os provedores e serviços de IA.
- `scripts/build_android.ps1`: Script PowerShell para build de artefatos APK/AAB.
- `assets/`: Armazenamento de ícones, fontes e logos.

## ⚙️ Setup Rápido

### Pré-requisitos
Certifique-se de ter o **Python 3.14** instalado na sua máquina.

### Instalação e Execução

1. Crie e ative o ambiente virtual:
   ```bash
   python -m venv .venv
