diff --git a/c:\Users\Belchior\IdeaProjects\Quiz Vance App\README.md b/c:\Users\Belchior\IdeaProjects\Quiz Vance App\README.md
new file mode 100644
--- /dev/null
+++ b/c:\Users\Belchior\IdeaProjects\Quiz Vance App\README.md
@@ -0,0 +1,71 @@
+# Quiz Vance App
+
+Aplicativo completo de estudo assistido por IA, focado em geração rápida de questões, flashcards e planos semanais. Construído em Python com Flet, multiplataforma (desktop, web, Android) e pronto para crescer.
+
+## Destaques
+- Questões objetivas com feedback imediato e modo prova com cronômetro.
+- Flashcards gerados por IA com revisão ativa e registro de progresso.
+- Suporte a uploads de PDF/TXT/MD para personalizar quizzes.
+- Biblioteca local, plano de estudos semanal e painel de estatísticas.
+- Tema claro/escuro persistente e navegação responsiva.
+- Build Android via `flet build apk` (script incluso).
+
+## Stack Técnica
+- **Framework UI**: Flet 0.80.x (Flutter sob o capô).
+- **Linguagem**: Python 3.14.
+- **IA**: Google Gemini (`google-genai`) e OpenAI (`openai`), com fallback econômico.
+- **Banco local**: SQLite (via `core/database_v2.py`).
+
+## Estrutura Rápida
+- `main_v2.py`: shell, rotas, views, regras de negócio.
+- `ui/views/login_view_v2.py`: autenticação e onboarding.
+- `core/ai_service_v2.py`: providers e serviços de IA.
+- `scripts/build_android.ps1`: build APK/AAB.
+- `assets/`: ícones e logo.
+
+## Setup de Desenvolvimento
+```bash
+python -m venv .venv
+.venv\Scripts\pip install -r requirements.txt
+```
+
+Executar app (desktop):
+```bash
+.venv\Scripts\python run.py
+```
+
+Testes:
+```bash
+.venv\Scripts\python -m pytest
+```
+
+## Build Android (APK)
+Pré-requisitos: Flutter SDK 3.38.x, JDK 17, Android SDK.
+```powershell
+powershell -ExecutionPolicy Bypass -File .\scripts\build_android.ps1 -Target apk
+```
+Artefato final: `build\apk\app-release.apk`.
+
+## Configuração de IA
+1. Obtenha sua API key:
+   - Gemini: https://aistudio.google.com/app/apikey
+   - OpenAI: https://platform.openai.com/api-keys
+2. Cole a chave em **Configurações > IA**, escolha provider e modelo.
+3. Opcional: ative “Modo economia” para modelos mais baratos.
+
+## UX e Responsividade
+- Layout responsivo com `ResponsiveRow` e tolerância a múltiplos tamanhos de tela.
+- Temas claro/escuro persistentes.
+- Modo contínuo e recursos premium são controlados por estado do usuário.
+
+## Segurança e Permissões
+- Apenas `INTERNET` no Android; uploads usam SAF do FilePicker.
+- Chaves de IA ficam armazenadas localmente.
+
+## Roadmap Curto
+- Migrar warning do `google.genai` para novas versões.
+- Melhorar onboarding visual e telemetria opcional.
+- Exportar flashcards/quiz em CSV/JSON.
+
+## Suporte
+Abra uma issue no GitHub com descrição clara e passos para reproduzir. Pull requests são bem-vindos.
