<div align="center">
  <img src="assets/logo_quizvance.png" alt="Quiz Vance" width="240" />
  <h1>Quiz Vance App</h1>
  <p>Estudo assistido por IA · Questões · Flashcards · Planos Semanais · Android & Desktop</p>
  <a href="#destaques"><strong>Destaques</strong></a> ·
  <a href="#stack">Stack</a> ·
  <a href="#setup">Setup</a> ·
  <a href="#build-android">Build Android</a> ·
  <a href="#ia">Configurar IA</a> ·
  <a href="#roadmap">Roadmap</a>
</div>

<hr/>

<h2 id="destaques">✨ Destaques</h2>
<ul>
  <li>Questões objetivas com feedback imediato e modo prova com cronômetro.</li>
  <li>Flashcards gerados por IA, revisão ativa e registro de progresso.</li>
  <li>Upload de PDF/TXT/MD para quizzes personalizados e biblioteca local.</li>
  <li>Plano semanal com IA, estatísticas e tema claro/escuro persistente.</li>
  <li>Build Android pronto via <code>flet build apk</code> (script incluso).</li>
</ul>

<h2 id="stack">🧩 Stack Técnica</h2>
<ul>
  <li><strong>UI</strong>: Flet 0.80.x (Flutter under the hood).</li>
  <li><strong>Linguagem</strong>: Python 3.14.</li>
  <li><strong>IA</strong>: Google Gemini (<code>google-genai</code>) e OpenAI (<code>openai</code>), com fallback econômico.</li>
  <li><strong>Banco local</strong>: SQLite (ver <code>core/database_v2.py</code>).</li>
</ul>

<h2 id="estrutura">📂 Estrutura Rápida</h2>
<ul>
  <li><code>main_v2.py</code>: shell, rotas, views, regras.</li>
  <li><code>ui/views/login_view_v2.py</code>: autenticação/onboarding.</li>
  <li><code>core/ai_service_v2.py</code>: providers IA.</li>
  <li><code>scripts/build_android.ps1</code>: build APK/AAB.</li>
  <li><code>assets/</code>: ícones e logo.</li>
</ul>

<h2 id="setup">⚙️ Setup Rápido</h2>
<pre>
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python run.py   # executa o app
.venv\Scripts\python -m pytest # roda testes
</pre>

<h2 id="build-android">📱 Build Android (APK)</h2>
<p>Pré-requisitos: Flutter 3.38.x, JDK 17, Android SDK.</p>
<pre>
powershell -ExecutionPolicy Bypass -File .\scripts\build_android.ps1 -Target apk
</pre>
<p>Saída: <code>build\apk\app-release.apk</code></p>

<h2 id="ia">🤖 Configurar IA (passo a passo rápido)</h2>
<ol>
  <li>Obtenha sua API key:
    <ul>
      <li><a href="https://aistudio.google.com/app/apikey">Gemini</a></li>
      <li><a href="https://platform.openai.com/api-keys">OpenAI</a></li>
    </ul>
  </li>
  <li>No app: <strong>Configurações &gt; IA</strong>, escolha provider e modelo.</li>
  <li>Cole a key, opcionalmente ative “Modo economia”.</li>
</ol>

<h2 id="ux">🖥️ UX e Responsividade</h2>
<ul>
  <li>Layout responsivo com <code>ResponsiveRow</code>, tema claro/escuro persistente.</li>
  <li>Modo contínuo e recursos premium controlados por estado do usuário.</li>
</ul>

<h2 id="seguranca">🔒 Segurança & Permissões</h2>
<ul>
  <li>Android: apenas <code>INTERNET</code>; uploads usam SAF do FilePicker.</li>
  <li>Chaves de IA armazenadas localmente.</li>
</ul>

<h2 id="roadmap">🛣️ Roadmap Curto</h2>
<ul>
  <li>Mitigar DeprecationWarning do <code>google.genai</code>.</li>
  <li>Onboarding visual aprimorado e telemetria opt-in.</li>
  <li>Exportar flashcards/quiz para CSV/JSON.</li>
</ul>

<h2 id="suporte">🤝 Suporte</h2>
<p>Abra uma issue no GitHub com passos claros para reproduzir. PRs são bem-vindos.</p>
