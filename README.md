<div align="center">
  <img src="assets/logo_quizvance.png" alt="Quiz Vance" width="220" />
  
  <h1>Aplicativo Quiz Vance</h1>

  <p>
    <strong>Plataforma Inteligente de Estudos Assistidos por IA</strong><br/>
    Questões • Flashcards • Planos Estratégicos • Android & Desktop
  </p>

  <p>
    <a href="#-visão-geral"><strong>Visão Geral</strong></a> ·
    <a href="#-proposta-de-valor"><strong>Proposta de Valor</strong></a> ·
    <a href="#-stack-técnica"><strong>Stack</strong></a> ·
    <a href="#-estrutura-do-projeto"><strong>Estrutura</strong></a> ·
    <a href="#-setup-de-desenvolvimento"><strong>Setup</strong></a> ·
    <a href="#-build-android"><strong>Build Android</strong></a> ·
    <a href="#-configuração-de-ia"><strong>Configurar IA</strong></a> ·
    <a href="#-roadmap"><strong>Roadmap</strong></a>
  </p>
</div>

---

## 📌 Visão Geral

O **Quiz Vance App** é uma plataforma multiplataforma de estudos assistida por Inteligência Artificial, projetada para acelerar a preparação acadêmica por meio de geração estruturada de conteúdo.

A aplicação combina **questões objetivas**, **flashcards inteligentes** e **planejamento semanal**, com foco em produtividade, retenção e escalabilidade técnica.

Construído com **Python + Flet (Flutter engine)**, o projeto foi arquitetado para suportar evolução contínua, modularização e integração com múltiplos provedores de IA.

---

## 🚀 Proposta de Valor

- Geração dinâmica de questões com feedback imediato e estruturado  
- Modo prova com cronômetro e simulação realista  
- Flashcards inteligentes com revisão ativa e acompanhamento de progresso  
- Upload de materiais (PDF / TXT / MD) para criação de quizzes personalizados  
- Biblioteca local de conteúdos e organização por estudo  
- Plano semanal assistido por IA, com priorização de tópicos  
- Estatísticas e indicadores de desempenho  
- Tema claro/escuro persistente e navegação responsiva  
- Build Android automatizado via script  

---

## 🧩 Stack Técnica

| Camada | Tecnologia |
|-------|------------|
| UI | Flet 0.80.x (Flutter engine) |
| Linguagem | Python 3.14 |
| IA | Google Gemini (`google-genai`) + OpenAI (`openai`) |
| Persistência | SQLite |
| Testes | Pytest |
| Build Android | Flutter SDK + JDK 17 + Android SDK |

---

## 📂 Estrutura do Projeto


Quiz Vance App/
│
├── main_v2.py                 # Shell principal, rotas, views e regras
├── run.py                     # Entry point da aplicação
├── core/
│   ├── ai_service_v2.py       # Serviços e providers de IA
│   └── database_v2.py         # Persistência (SQLite)
├── ui/views/
│   └── login_view_v2.py       # Autenticação e onboarding
├── scripts/
│   └── build_android.ps1      # Build APK/AAB
└── assets/                    # Identidade visual (ícones, logo)

</code></pre>

  <p>
    A arquitetura separa claramente as camadas de UI, domínio, integrações externas (IA) e persistência,
    facilitando manutenção, testes e escalabilidade.
  </p>

  <h2 id="ambiente">⚙️ Ambiente de Desenvolvimento</h2>

  <h3>1) Criar ambiente virtual</h3>
  <pre><code>python -m venv .venv
.venv\Scripts\pip install -r requirements.txt</code></pre>

  <h3>2) Executar aplicação (Desktop)</h3>
  <pre><code>.venv\Scripts\python run.py</code></pre>

  <h3>3) Executar testes</h3>
  <pre><code>.venv\Scripts\python -m pytest</code></pre>

  <h2 id="android">📱 Build Android</h2>

  <h3>Pré-requisitos</h3>
  <ul>
    <li>Flutter SDK 3.38.x</li>
    <li>JDK 17</li>
    <li>Android SDK configurado</li>
  </ul>

  <h3>Gerar APK</h3>
  <pre><code>powershell -ExecutionPolicy Bypass -File .\scripts\build_android.ps1 -Target apk</code></pre>

  <p><strong>Artefato final:</strong> <code>build\apk\app-release.apk</code></p>

  <h2 id="ia">🤖 Configuração de Inteligência Artificial</h2>
  <p>
    A aplicação suporta múltiplos provedores com estratégia de fallback, priorizando continuidade e custo-benefício.
  </p>

  <h3>Obtenha sua chave de API</h3>
  <ul>
    <li>Google Gemini → <a href="https://aistudio.google.com/app/apikey">aistudio.google.com/app/apikey</a></li>
    <li>OpenAI → <a href="https://platform.openai.com/api-keys">platform.openai.com/api-keys</a></li>
  </ul>

  <h3>Configuração no App</h3>
  <ol>
    <li>Acesse <strong>Configurações → IA</strong>.</li>
    <li>Selecione o provedor e o modelo.</li>
    <li>Insira a API key.</li>
    <li>(Opcional) Ative o modo econômico.</li>
  </ol>

  <p><em>Observação:</em> as chaves são armazenadas localmente.</p>

  <h2 id="ux">🖥 UX &amp; Engenharia de Interface</h2>
  <ul>
    <li>Layout responsivo com <code>ResponsiveRow</code>.</li>
    <li>Compatibilidade com múltiplas resoluções e densidades de tela.</li>
    <li>Tema claro/escuro persistente.</li>
    <li>Controle de recursos premium por estado do usuário.</li>
    <li>Estrutura preparada para modularização futura.</li>
  </ul>

  <h2 id="seguranca">🔐 Segurança</h2>
  <ul>
    <li>Android: permissão restrita a <code>INTERNET</code>.</li>
    <li>Uploads via SAF (Storage Access Framework).</li>
    <li>Armazenamento local de chaves.</li>
    <li>Sem dependência de backend próprio.</li>
  </ul>

  <h2 id="roadmap">📈 Roadmap Estratégico</h2>
  <ul>
    <li>Atualização para novas versões do <code>google.genai</code> e mitigação de avisos de depreciação.</li>
    <li>Implementação de telemetria <em>opt-in</em>.</li>
    <li>Exportação de quizzes e flashcards (CSV / JSON).</li>
    <li>Suporte futuro a sincronização em nuvem.</li>
    <li>Gamificação e métricas avançadas de retenção.</li>
  </ul>

  <h2 id="contribuicao">🤝 Contribuição</h2>
  <p>Contribuições são bem-vindas.</p>
  <ol>
    <li>Faça um fork do repositório.</li>
    <li>Crie uma branch para sua alteração.</li>
    <li>Envie um Pull Request descrevendo claramente o impacto.</li>
  </ol>
  <p>Para issues, inclua passos objetivos para reprodução.</p>

  <h2 id="licenca">📄 Licença</h2>
  <p>Definir licença (MIT, Apache 2.0, etc.) conforme a estratégia do projeto.</p>

  <hr />

  <p>
    <strong>Fonte:</strong> versão baseada e aprimorada a partir do arquivo existente.
  </p>
</body>
</html>
