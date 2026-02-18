<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Quiz Vance App — README</title>
</head>

<body>
  <div align="center">
    <img src="assets/logo_quizvance.png" alt="Quiz Vance Logo" width="220" />
    <h1>Quiz Vance App</h1>
    <h3>Plataforma Inteligente de Estudos Assistida por IA</h3>
    <p><em>Questões • Flashcards • Planos Estratégicos • Android &amp; Desktop</em></p>

    <p>
      <a href="#visao-geral"><strong>Visão Geral</strong></a> ·
      <a href="#proposta-de-valor"><strong>Proposta de Valor</strong></a> ·
      <a href="#arquitetura"><strong>Arquitetura</strong></a> ·
      <a href="#estrutura"><strong>Estrutura</strong></a> ·
      <a href="#ambiente"><strong>Setup</strong></a> ·
      <a href="#android"><strong>Build Android</strong></a> ·
      <a href="#ia"><strong>Configurar IA</strong></a> ·
      <a href="#ux"><strong>UX</strong></a> ·
      <a href="#seguranca"><strong>Segurança</strong></a> ·
      <a href="#roadmap"><strong>Roadmap</strong></a> ·
      <a href="#contribuicao"><strong>Contribuição</strong></a> ·
      <a href="#licenca"><strong>Licença</strong></a>
    </p>
  </div>

  <hr />

  <h2 id="visao-geral">📌 Visão Geral</h2>
  <p>
    O <strong>Quiz Vance App</strong> é uma plataforma multiplataforma de estudos assistida por Inteligência Artificial,
    projetada para otimizar o aprendizado por meio de geração dinâmica de conteúdo educacional.
  </p>
  <p>
    A aplicação integra geração de questões, criação inteligente de flashcards e planejamento semanal estratégico,
    com foco em produtividade, retenção e escalabilidade técnica.
  </p>
  <p>
    Desenvolvido em <strong>Python com Flet (Flutter under the hood)</strong>, o projeto foi arquitetado para suportar
    expansão contínua, modularização e integração com múltiplos provedores de IA.
  </p>

  <h2 id="proposta-de-valor">🚀 Proposta de Valor</h2>
  <ul>
    <li>Geração instantânea de questões com feedback estruturado.</li>
    <li>Modo prova com cronômetro e simulação realista.</li>
    <li>Flashcards inteligentes com revisão ativa e registro de progresso.</li>
    <li>Upload de materiais (PDF / TXT / MD) para personalização e biblioteca local.</li>
    <li>Plano de estudos semanal gerado por IA, com foco em priorização.</li>
    <li>Painel de estatísticas e acompanhamento de evolução.</li>
    <li>Suporte a Android (APK) e Desktop.</li>
    <li>Arquitetura preparada para crescimento.</li>
  </ul>

  <h2 id="arquitetura">🧠 Arquitetura Técnica</h2>

  <h3>Stack Principal</h3>
  <table border="1" cellpadding="8" cellspacing="0">
    <thead>
      <tr>
        <th align="left">Camada</th>
        <th align="left">Tecnologia</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>Interface</td>
        <td>Flet 0.80.x (Flutter engine)</td>
      </tr>
      <tr>
        <td>Linguagem</td>
        <td>Python 3.14</td>
      </tr>
      <tr>
        <td>IA</td>
        <td>Google Gemini (<code>google-genai</code>) + OpenAI (<code>openai</code>)</td>
      </tr>
      <tr>
        <td>Persistência</td>
        <td>SQLite</td>
      </tr>
      <tr>
        <td>Build Mobile</td>
        <td>Flet Build + Flutter SDK</td>
      </tr>
      <tr>
        <td>Testes</td>
        <td>Pytest</td>
      </tr>
    </tbody>
  </table>

  <h2 id="estrutura">🏗 Estrutura do Projeto</h2>
  <pre><code>Quiz Vance App/
│
├── main_v2.py                 # Shell principal, rotas e regras
├── run.py                     # Entry point da aplicação
├── core/
│   ├── ai_service_v2.py       # Camada de integração com IA
│   └── database_v2.py         # Persistência SQLite
├── ui/views/
│   └── login_view_v2.py       # Autenticação e onboarding
├── scripts/
│   └── build_android.ps1      # Script de build APK/AAB
└── assets/                    # Ícones e identidade visual
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
