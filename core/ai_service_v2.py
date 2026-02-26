# -*- coding: utf-8 -*-
"""
ServiÃ§o de AI Multi-Provider (Gemini + OpenAI)
Suporta Google Gemini e OpenAI GPT
"""

# -*- coding: utf-8 -*-
import json
import random
import time
import datetime
import warnings
import sys
import os
import re
from typing import Optional, Dict, List, Any
from abc import ABC, abstractmethod

try:
    from core.error_monitor import log_event
except Exception:
    def log_event(name: str, data: str = "") -> None:
        _ = (name, data)

# Configurar encoding para UTF-8 em Windows
os.environ['PYTHONIOENCODING'] = 'utf-8'
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

# Lazy imports para reduzir latencia de startup.
genai = None
OpenAI = None
GEMINI_AVAILABLE = None
OPENAI_AVAILABLE = None


def _ensure_gemini_available() -> bool:
    global genai, GEMINI_AVAILABLE
    if GEMINI_AVAILABLE is not None:
        return bool(GEMINI_AVAILABLE)
    try:
        from google import genai as _genai
        genai = _genai
        GEMINI_AVAILABLE = True
    except Exception:
        GEMINI_AVAILABLE = False
    return bool(GEMINI_AVAILABLE)


def _ensure_openai_available() -> bool:
    global OpenAI, OPENAI_AVAILABLE
    if OPENAI_AVAILABLE is not None:
        return bool(OPENAI_AVAILABLE)
    try:
        from openai import OpenAI as _OpenAI
        OpenAI = _OpenAI
        OPENAI_AVAILABLE = True
    except Exception:
        OPENAI_AVAILABLE = False
    return bool(OPENAI_AVAILABLE)


# ========== CLASSE BASE ==========
class AIProvider(ABC):
    """Classe base para providers de AI"""
    
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
    
    @abstractmethod
    def generate_text(self, prompt: str) -> Optional[str]:
        """Gera texto a partir de um prompt"""
        pass
    
    def extract_json_object(self, text: str) -> Optional[Dict]:
        """Extrai objeto JSON de texto"""
        try:
            text = text.strip().replace("```json", "").replace("```", "")
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                return json.loads(text[start:end + 1])
            return None
        except Exception:
            return None
    
    def extract_json_list(self, text: str) -> Optional[List]:
        """Extrai lista JSON de texto"""
        try:
            text = text.strip().replace("```json", "").replace("```", "")
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1:
                return json.loads(text[start:end + 1])
            return None
        except Exception:
            return None


# ========== GEMINI PROVIDER ==========
class GeminiProvider(AIProvider):
    """Provider para Google Gemini"""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        super().__init__(api_key, model)
        if not _ensure_gemini_available():
            raise ImportError("google-genai nao esta instalado")
        self.client = genai.Client(api_key=api_key)
        self.last_error_kind = ""
        self.last_error_message = ""
        self._fallback_models = self._build_fallback_models(model)

    def _build_fallback_models(self, model: str) -> List[str]:
        preferred = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-3-flash-preview",
            "gemini-2.5-pro",
            "gemini-3-pro-preview",
        ]
        return [model] + [m for m in preferred if m != model]

    def _classify_error(self, message: str) -> str:
        msg = (message or "").lower()
        if "429" in msg or "quota exceeded" in msg or "rate limit" in msg:
            if "limit: 0" in msg or "perday" in msg or "per day" in msg:
                return "quota_hard"
            return "quota_soft"
        if "timeout" in msg or "temporar" in msg or "unavailable" in msg:
            return "transient"
        return "other"

    def generate_text(self, prompt: str) -> Optional[str]:
        """Gera texto usando Gemini"""
        self.last_error_kind = ""
        self.last_error_message = ""

        for idx, candidate_model in enumerate(self._fallback_models):
            try:
                response = self.client.models.generate_content(model=candidate_model, contents=prompt)
                text = getattr(response, "text", None)
                if text:
                    self.model = candidate_model
                    if idx > 0:
                        print(f"[GEMINI] Fallback ativado com sucesso: {candidate_model}")
                    return text
            except Exception as e:
                msg = str(e)
                kind = self._classify_error(msg)
                self.last_error_kind = kind
                self.last_error_message = msg
                print(f"[GEMINI] Erro ({candidate_model}): {e}")
                if kind in ("quota_hard", "quota_soft") and idx < len(self._fallback_models) - 1:
                    continue
                if kind not in ("quota_hard", "quota_soft"):
                    break

        return None
# ========== OPENAI PROVIDER ==========
class OpenAIProvider(AIProvider):
    """Provider para OpenAI GPT"""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        super().__init__(api_key, model)
        if not _ensure_openai_available():
            raise ImportError("openai nÃ£o estÃ¡ instalado")
        self.client = OpenAI(api_key=api_key)
        self.last_error_kind = ""
        self.last_error_message = ""

    def _classify_error(self, message: str) -> str:
        msg = (message or "").lower()
        if "rate limit" in msg or "quota" in msg or "429" in msg:
            return "quota_soft" if "per" in msg else "quota_hard"
        if "insufficient_quota" in msg:
            return "quota_hard"
        if "401" in msg or "unauthorized" in msg or "invalid api key" in msg:
            return "auth"
        if "timeout" in msg or "temporar" in msg or "unavailable" in msg:
            return "transient"
        return "other"
    
    def generate_text(self, prompt: str) -> Optional[str]:
        """Gera texto usando OpenAI"""
        self.last_error_kind = ""
        self.last_error_message = ""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e:
            msg = str(e)
            self.last_error_kind = self._classify_error(msg)
            self.last_error_message = msg
            print(f"[OPENAI] Erro: {e}")
            return None


# ========== FACTORY ==========
def create_ai_provider(provider_type: str, api_key: str, model: Optional[str] = None) -> AIProvider:
    """
    Cria provider de AI
    
    Args:
        provider_type: "gemini" ou "openai"
        api_key: Chave API
        model: Modelo especÃ­fico (opcional)
    
    Returns:
        Instance de AIProvider
    """
    if provider_type == "gemini":
        model = model or "gemini-2.5-flash"
        return GeminiProvider(api_key, model)
    elif provider_type == "openai":
        model = model or "gpt-4o-mini"
        return OpenAIProvider(api_key, model)
    else:
        raise ValueError(f"Provider desconhecido: {provider_type}")


# ========== SERVIÃ‡O DE AI ==========
class AIService:
    """ServiÃ§o centralizado de AI"""
    
    def __init__(self, provider: AIProvider, telemetry_opt_in: bool = False, user_anon: str = "anon"):
        self.provider = provider
        self.telemetry_opt_in = bool(telemetry_opt_in)
        self.user_anon = str(user_anon or "anon")

    def _emit_ai_event(
        self,
        event_name: str,
        feature_name: str,
        latency_ms: int = 0,
        error_code: str = "",
    ) -> None:
        if not self.telemetry_opt_in:
            return
        provider_name = str(self.provider.__class__.__name__.replace("Provider", "")).lower()
        payload = {
            "timestamp": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "feature_name": str(feature_name or "unknown"),
            "provider": provider_name,
            "model": str(getattr(self.provider, "model", "") or ""),
            "latency_ms": int(max(0, latency_ms or 0)),
            "error_code": str(error_code or ""),
            "user_anon": self.user_anon,
        }
        try:
            log_event(event_name, json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass

    def _call_provider_text(self, prompt: str, feature_name: str) -> Optional[str]:
        started = time.perf_counter()
        self._emit_ai_event("ai_call_started", feature_name=feature_name)
        error_code = ""
        try:
            text = self.provider.generate_text(prompt)
            if not text:
                error_code = self._provider_error_kind() or "empty_response"
            return text
        except Exception:
            error_code = "exception"
            raise
        finally:
            latency = int(max(0.0, (time.perf_counter() - started) * 1000.0))
            self._emit_ai_event(
                "ai_call_finished",
                feature_name=feature_name,
                latency_ms=latency,
                error_code=error_code,
            )
    
    def _normalize_quiz(self, data: Dict) -> Optional[Dict]:
        """Normaliza dados de quiz"""
        if not isinstance(data, dict):
            return None
        
        # Extrair pergunta
        pergunta = (
            data.get("pergunta") or
            data.get("question") or
            data.get("enunciado") or
            data.get("pergunta_texto")
        )
        
        # Extrair opÃ§Ãµes
        opcoes = (
            data.get("opcoes") or
            data.get("opÃ§Ãµes") or
            data.get("alternativas") or
            data.get("choices") or
            data.get("options")
        )
        
        # Extrair resposta correta
        correta = data.get("correta_index") or data.get("indice_correto")
        if correta is None:
            correta = (
                data.get("resposta_correta") or
                data.get("answer") or
                data.get("correct_answer")
            )
        
        # Extrair explicaÃ§Ã£o
        explicacao = (
            data.get("explicacao") or
            data.get("explicaÃ§Ã£o") or
            data.get("justificativa") or
            data.get("feedback") or
            data.get("explanation") or
            ""
        )
        
        # ValidaÃ§Ãµes
        if not isinstance(pergunta, str) or not pergunta.strip():
            return None
        if not isinstance(opcoes, list) or len(opcoes) < 2:
            return None
        
        # Normalizar opÃ§Ãµes
        opcoes_norm = []
        for op in opcoes:
            if isinstance(op, dict):
                texto = (
                    op.get("texto") or
                    op.get("text") or
                    op.get("opcao") or
                    op.get("option")
                )
                if texto is not None:
                    opcoes_norm.append(str(texto))
            else:
                opcoes_norm.append(str(op))
        
        opcoes_norm = [o.strip() for o in opcoes_norm if o and str(o).strip()]
        if len(opcoes_norm) < 2:
            return None
        if len(opcoes_norm) > 4:
            opcoes_norm = opcoes_norm[:4]
        
        # Normalizar Ã­ndice correto
        correta_idx = None
        if isinstance(correta, int):
            correta_idx = correta
        elif isinstance(correta, str):
            c = correta.strip().upper()
            if c in ("A", "B", "C", "D"):
                correta_idx = ["A", "B", "C", "D"].index(c)
            else:
                try:
                    correta_idx = int(c)
                except Exception:
                    correta_idx = None
        
        if correta_idx is None:
            correta_idx = 0
        correta_idx = max(0, min(correta_idx, len(opcoes_norm) - 1))
        
        return {
            "pergunta": pergunta.strip(),
            "opcoes": opcoes_norm,
            "correta_index": correta_idx,
            "explicacao": str(explicacao).strip()
        }

    def validate_task_payload(self, task: str, payload: Any) -> tuple[bool, str]:
        task_name = str(task or "").strip().lower()
        if task_name == "quiz":
            if not isinstance(payload, dict):
                return False, "quiz_payload_not_dict"
            pergunta = str(payload.get("pergunta") or "").strip()
            opcoes = payload.get("opcoes")
            try:
                correta_index = int(payload.get("correta_index", 0))
            except Exception:
                return False, "quiz_correta_index_invalid"
            if not pergunta:
                return False, "quiz_pergunta_empty"
            if not isinstance(opcoes, list) or len(opcoes) < 2:
                return False, "quiz_opcoes_invalid"
            if correta_index < 0 or correta_index >= len(opcoes):
                return False, "quiz_correta_out_of_range"
            return True, "ok"
        if task_name == "flashcard":
            if not isinstance(payload, dict):
                return False, "flashcard_payload_not_dict"
            frente = str(payload.get("frente") or "").strip()
            verso = str(payload.get("verso") or "").strip()
            if not frente or not verso:
                return False, "flashcard_missing_fields"
            return True, "ok"
        if task_name == "study_plan_item":
            if not isinstance(payload, dict):
                return False, "study_plan_item_not_dict"
            if not str(payload.get("dia") or "").strip():
                return False, "study_plan_day_empty"
            if not str(payload.get("tema") or "").strip():
                return False, "study_plan_theme_empty"
            return True, "ok"
        if task_name == "study_summary":
            if not isinstance(payload, dict):
                return False, "study_summary_not_dict"
            required_keys = ["titulo", "resumo_curto", "topicos_principais", "checklist_de_estudo"]
            for key in required_keys:
                if key not in payload:
                    return False, f"study_summary_missing_{key}"
            return True, "ok"
        return False, "task_not_supported"

    def _provider_error_kind(self) -> str:
        provider = getattr(self, "provider", None)
        return str(getattr(provider, "last_error_kind", "") or "").strip().lower()

    def _should_abort_retry(self) -> bool:
        """Evita repeticao de chamadas quando erro e terminal para a sessao."""
        return self._provider_error_kind() in {"quota_hard", "quota_soft", "auth"}

    def _build_quiz_context(self, content: Optional[List[str]], topic: Optional[str]) -> Optional[str]:
        contexto = ""
        if content:
            sample_size = min(4, len(content))
            try:
                amostra = random.sample(content, sample_size)
            except Exception:
                amostra = list(content[:sample_size])
            texto_base = "\n".join(amostra)[:6000]
            contexto = f"Baseado no texto:\n{texto_base}\n"
            if topic:
                contexto += f"\nFoque no topico: {topic}."
        elif topic:
            contexto = f"Voce e um professor especialista. Gere questoes tecnicas sobre: '{topic}'."
        return contexto or None

    def _normalize_quiz_batch_payload(self, data: Any, limit: int) -> List[Dict]:
        itens = []
        if isinstance(data, list):
            itens = data
        elif isinstance(data, dict):
            for key in ("questoes", "questions", "itens", "items"):
                payload = data.get(key)
                if isinstance(payload, list):
                    itens = payload
                    break
            if not itens:
                itens = [data]
        result = []
        seen = set()
        safe_limit = max(1, int(limit or 1))
        for item in itens:
            quiz = self._normalize_quiz(item if isinstance(item, dict) else {})
            if not quiz:
                continue
            key = quiz.get("pergunta", "").strip().lower()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            result.append(quiz)
            if len(result) >= safe_limit:
                break
        return result

    def generate_quiz_batch(
        self,
        content: Optional[List[str]] = None,
        topic: Optional[str] = None,
        difficulty: str = "Medio",
        quantity: int = 3,
        retries: int = 2,
    ) -> List[Dict]:
        """
        Gera varias questoes em uma unica chamada para reduzir latencia/custo.
        """
        quantidade = max(1, min(10, int(quantity or 1)))
        tentativas = max(1, int(retries or 1))
        contexto = self._build_quiz_context(content, topic)
        if not contexto:
            print("[AI] Sem conteudo ou topico")
            return []

        prompt = f"""
{contexto}

Crie {quantidade} questoes de multipla escolha nivel {difficulty}.

IMPORTANTE: Responda APENAS com JSON valido, sem texto adicional.

Formato JSON obrigatorio:
[
  {{
    "pergunta": "Texto da pergunta...",
    "opcoes": ["A. Primeira opcao", "B. Segunda opcao", "C. Terceira opcao", "D. Quarta opcao"],
    "correta_index": 0,
    "explicacao": "Explicacao breve da resposta correta..."
  }}
]
"""

        for attempt in range(tentativas):
            try:
                text = self._call_provider_text(prompt, "quiz_batch")
                if not text:
                    if self._should_abort_retry():
                        break
                    continue

                data = self.provider.extract_json_list(text)
                if data is None:
                    data = self.provider.extract_json_object(text)

                normalizadas = self._normalize_quiz_batch_payload(data, quantidade)
                normalizadas = [q for q in normalizadas if self.validate_task_payload("quiz", q)[0]]
                if normalizadas:
                    print(f"[AI] [OK] {len(normalizadas)} questoes geradas em lote")
                    return normalizadas

                print(f"[AI] Tentativa {attempt + 1}: lote invalido")
            except Exception as e:
                print(f"[AI] Tentativa {attempt + 1} erro em lote: {e}")
                if self._should_abort_retry():
                    break

            if attempt < tentativas - 1:
                time.sleep(0.35)

        print("[AI] [ERRO] Falha ao gerar lote de questoes")
        return []
    
    def generate_quiz(
        self,
        content: Optional[List[str]] = None,
        topic: Optional[str] = None,
        difficulty: str = "Medio",
        retries: int = 2
    ) -> Optional[Dict]:
        """
        Gera uma questÃ£o de mÃºltipla escolha
        
        Args:
            content: Lista de textos (do PDF)
            topic: TÃ³pico especÃ­fico
            difficulty: Dificuldade
            retries: Tentativas
        
        Returns:
            Dict com pergunta, opÃ§Ãµes, resposta correta e explicaÃ§Ã£o
        """
        lote = self.generate_quiz_batch(
            content=content,
            topic=topic,
            difficulty=difficulty,
            quantity=1,
            retries=retries,
        )
        if lote:
            return lote[0]
        print("[AI] [ERRO] Falha ao gerar quiz apos todas as tentativas")
        return None

    def _normalize_flashcard(self, item: Dict) -> Optional[Dict]:
        if not isinstance(item, dict):
            return None
        frente = (
            item.get("frente")
            or item.get("front")
            or item.get("pergunta")
            or item.get("question")
            or item.get("titulo")
            or ""
        )
        verso = (
            item.get("verso")
            or item.get("back")
            or item.get("resposta")
            or item.get("answer")
            or item.get("explicacao")
            or ""
        )
        frente = str(frente).strip()
        verso = str(verso).strip()
        if not frente or not verso:
            return None
        return {"frente": frente, "verso": verso}

    def generate_flashcards(
        self,
        content: List[str],
        quantity: int = 5,
        retries: int = 2
    ) -> List[Dict]:
        """
        Gera flashcards
        
        Args:
            content: Textos do PDF
            quantity: Quantidade de flashcards
            retries: Tentativas
        
        Returns:
            Lista de dicts com 'frente' e 'verso'
        """
        if not content:
            return []

        quantidade = max(1, min(20, int(quantity or 5)))
        tentativas = max(1, int(retries or 1))
        texto_amostra = "\n".join(random.sample(content, min(4, len(content))))[:6000]

        prompt = f"""
Gere {quantidade} flashcards do texto abaixo.

IMPORTANTE: Responda APENAS com JSON vÃ¡lido, sem texto adicional.

Formato JSON obrigatÃ³rio:
[
  {{"frente": "Pergunta ou conceito...", "verso": "Resposta ou explicaÃ§Ã£o..."}},
  {{"frente": "...", "verso": "..."}}
]

Texto:
{texto_amostra}
"""

        for attempt in range(tentativas):
            try:
                text = self._call_provider_text(prompt, "flashcards")
                if not text:
                    if self._should_abort_retry():
                        break
                    continue

                data = self.provider.extract_json_list(text)
                if data is None:
                    data = self.provider.extract_json_object(text)
                    if isinstance(data, dict):
                        for key in ("flashcards", "cards", "itens", "items"):
                            maybe_list = data.get(key)
                            if isinstance(maybe_list, list):
                                data = maybe_list
                                break
                if isinstance(data, list) and len(data) > 0:
                    cards = []
                    seen = set()
                    for item in data:
                        card = self._normalize_flashcard(item if isinstance(item, dict) else {})
                        if not card:
                            continue
                        if not self.validate_task_payload("flashcard", card)[0]:
                            continue
                        key = card["frente"].lower()
                        if key in seen:
                            continue
                        seen.add(key)
                        cards.append(card)
                        if len(cards) >= quantidade:
                            break
                    if cards:
                        print(f"[AI] [OK] {len(cards)} flashcards gerados")
                        return cards

                print(f"[AI] Tentativa {attempt + 1}: Lista JSON invalida")

            except Exception as e:
                print(f"[AI] Tentativa {attempt + 1} erro: {e}")

                if self._should_abort_retry():
                    break
            if attempt < tentativas - 1:
                time.sleep(0.35)

        print("[AI] [ERRO] Falha ao gerar flashcards")
        return []
    
    def generate_open_question(
        self,
        content: List[str],
        difficulty: str = "MÃ©dio",
        retries: int = 2
    ) -> Optional[Dict]:
        """
        Gera pergunta dissertativa
        
        Returns:
            Dict com 'pergunta' e 'resposta_esperada'
        """
        if not content:
            return None
        
        texto_amostra = "\n".join(random.sample(content, min(2, len(content))))[:5000]
        
        prompt = f"""
Crie 1 pergunta dissertativa nÃ­vel {difficulty}.

IMPORTANTE: Responda APENAS com JSON vÃ¡lido, sem texto adicional.

Formato JSON obrigatÃ³rio:
{{
  "pergunta": "Pergunta dissertativa...",
  "resposta_esperada": "Resposta modelo esperada..."
}}

Texto:
{texto_amostra}
"""
        
        tentativas = max(1, int(retries or 1))
        for attempt in range(tentativas):
            try:
                text = self._call_provider_text(prompt, "open_question")
                if not text:
                    if self._should_abort_retry():
                        break
                    continue
                
                data = self.provider.extract_json_object(text)
                if data and "pergunta" in data:
                    print("[AI] [OK] Pergunta aberta gerada")
                    return data
                
                print(f"[AI] Tentativa {attempt + 1}: JSON invÃ¡lido")
                
            except Exception as e:
                print(f"[AI] Tentativa {attempt + 1} erro: {e}")
                if self._should_abort_retry():
                    break
            
            if attempt < tentativas - 1:
                time.sleep(0.35)
        
        print("[AI] [ERRO] Falha ao gerar pergunta aberta")
        return None
    
    def grade_open_answer(
        self,
        question: str,
        student_answer: str,
        expected_answer: str,
        retries: int = 2
    ) -> Dict:
        """
        Corrige resposta dissertativa
        
        Returns:
            Dict com 'nota', 'correto' e 'feedback'
        """
        prompt = f"""
Compare a resposta do aluno com o gabarito.

Pergunta: {question}

Gabarito: {expected_answer}

Resposta do aluno: {student_answer}

IMPORTANTE: Responda APENAS com JSON vÃ¡lido, sem texto adicional.

Formato JSON obrigatÃ³rio:
{{
  "nota": 85,
  "correto": true,
  "feedback": "Feedback detalhado sobre a resposta..."
}}

Nota de 0 a 100. Considere correto se nota >= 70.
"""
        
        tentativas = max(1, int(retries or 1))
        for attempt in range(tentativas):
            try:
                text = self._call_provider_text(prompt, "grade_open_answer")
                if not text:
                    if self._should_abort_retry():
                        break
                    continue
                
                data = self.provider.extract_json_object(text)
                if data and "nota" in data:
                    print(f"[AI] [OK] Resposta corrigida: {data.get('nota')}")
                    return data
                
                print(f"[AI] Tentativa {attempt + 1}: JSON invÃ¡lido")
                
            except Exception as e:
                print(f"[AI] Tentativa {attempt + 1} erro: {e}")
                if self._should_abort_retry():
                    break
            
            if attempt < tentativas - 1:
                time.sleep(0.35)
        
        print("[AI] âŒ Falha ao corrigir resposta")
        return {
            "nota": 0,
            "correto": False,
            "feedback": "Erro na correÃ§Ã£o automÃ¡tica."
        }

    def explain_simple(
        self,
        question: str,
        answer: str,
        retries: int = 2
    ) -> str:
        """
        Explica a questao de forma simples ("explain like I'm 5").
        """
        prompt = f"""
Voce e um professor experiente e didatico.
Explique o conceito por tras desta questao e por que a resposta e essa, de forma extremamente simples e direta.
Use analogias se possivel. Maximo de 3 paragrafos curtos.

Questao: {question}
Resposta Correta: {answer}

Explique para um estudante iniciante:
"""
        tentativas = max(1, int(retries or 1))
        for attempt in range(tentativas):
            try:
                text = self._call_provider_text(prompt, "explain_simple")
                if text:
                    return text.strip()
            except Exception as e:
                print(f"[AI] Tentativa {attempt + 1} erro: {e}")
                if self._should_abort_retry():
                    break
            if attempt < tentativas - 1:
                time.sleep(0.35)
        
        return "Nao foi possivel gerar uma explicacao simplificada no momento."

    def generate_study_plan(
        self,
        objetivo: str,
        data_prova: str,
        tempo_diario_min: int,
        topicos_prioritarios: Optional[List[str]] = None,
        retries: int = 2,
    ) -> List[Dict]:
        topicos = topicos_prioritarios or ["Geral"]
        prompt = f"""
Crie um plano de estudo de 7 dias em JSON.

Objetivo: {objetivo}
Data da prova: {data_prova}
Tempo diario (min): {tempo_diario_min}
Topicos prioritarios: {", ".join(topicos)}

Retorne APENAS JSON no formato:
[
  {{
    "dia": "Seg",
    "tema": "Tema principal",
    "atividade": "Questoes + revisao de erros",
    "duracao_min": 90,
    "prioridade": 1
  }}
]
"""
        tentativas = max(1, int(retries or 1))
        for attempt in range(tentativas):
            try:
                text = self._call_provider_text(prompt, "study_plan")
                if not text:
                    if self._should_abort_retry():
                        break
                    continue
                data = self.provider.extract_json_list(text)
                if isinstance(data, list) and data:
                    result = []
                    for item in data[:7]:
                        if not isinstance(item, dict):
                            continue
                        row = {
                            "dia": str(item.get("dia") or "Dia"),
                            "tema": str(item.get("tema") or "Geral"),
                            "atividade": str(item.get("atividade") or "Resolver questoes"),
                            "duracao_min": int(item.get("duracao_min") or tempo_diario_min),
                            "prioridade": int(item.get("prioridade") or 1),
                        }
                        if not self.validate_task_payload("study_plan_item", row)[0]:
                            continue
                        result.append(row)
                    if result:
                        return result
            except Exception:
                if self._should_abort_retry():
                    break
            if attempt < tentativas - 1:
                time.sleep(0.35)

        # Fallback deterministico
        dias = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
        fallback = []
        for i, d in enumerate(dias):
            tema = topicos[i % len(topicos)]
            fallback.append(
                {
                    "dia": d,
                    "tema": tema,
                    "atividade": "Questoes (60%) + flashcards (20%) + revisao de erros (20%)",
                    "duracao_min": tempo_diario_min,
                    "prioridade": 1 if i < 3 else 2,
                }
            )
        return fallback

    def generate_study_summary(
        self,
        content: List[str],
        topic: str = "",
        retries: int = 2,
    ) -> Dict:
        def _clean_text(value: Any, max_len: int = 280) -> str:
            text = re.sub(r"\s+", " ", str(value or "")).strip()
            if not text:
                return ""
            return text[:max_len]

        def _as_str_list(value: Any, max_items: int = 8, max_len: int = 180) -> List[str]:
            if not isinstance(value, list):
                return []
            out: List[str] = []
            seen = set()
            for item in value:
                text = _clean_text(item, max_len=max_len)
                if not text:
                    continue
                key = text.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(text)
                if len(out) >= max_items:
                    break
            return out

        def _as_definition_list(value: Any, max_items: int = 8) -> List[Dict]:
            if not isinstance(value, list):
                return []
            out: List[Dict] = []
            for item in value:
                if isinstance(item, dict):
                    termo = _clean_text(item.get("termo") or item.get("conceito") or item.get("titulo"), 90)
                    definicao = _clean_text(item.get("definicao") or item.get("descricao") or item.get("explicacao"), 240)
                else:
                    raw = _clean_text(item, 260)
                    if ":" in raw:
                        left, right = raw.split(":", 1)
                        termo = _clean_text(left, 90)
                        definicao = _clean_text(right, 240)
                    else:
                        termo = ""
                        definicao = raw
                if termo and definicao:
                    out.append({"termo": termo, "definicao": definicao})
                elif definicao:
                    out.append({"termo": "Conceito", "definicao": definicao})
                if len(out) >= max_items:
                    break
            return out

        def _normalize_dificuldade(value: Any) -> str:
            raw = _clean_text(value, 24).lower()
            if ("facil" in raw) or ("fácil" in raw) or ("easy" in raw):
                return "facil"
            if ("dificil" in raw) or ("difícil" in raw) or ("hard" in raw):
                return "dificil"
            return "medio"

        def _normalize_tags(value: Any, max_items: int = 6) -> List[str]:
            if isinstance(value, str):
                parts = [x.strip() for x in re.split(r"[;,|]", value) if x.strip()]
                return _as_str_list(parts, max_items=max_items, max_len=36)
            return _as_str_list(value, max_items=max_items, max_len=36)

        def _as_flashcard_suggestions(value: Any, max_items: int = 10) -> List[Dict]:
            if not isinstance(value, list):
                return []
            out: List[Dict] = []
            seen = set()
            for item in value:
                if isinstance(item, dict):
                    frente = _clean_text(item.get("frente") or item.get("front") or item.get("pergunta"), 140)
                    verso = _clean_text(item.get("verso") or item.get("back") or item.get("resposta"), 240)
                    tags = _normalize_tags(item.get("tags"))
                    dificuldade = _normalize_dificuldade(item.get("dificuldade"))
                else:
                    raw = _clean_text(item, 320)
                    if "->" in raw:
                        left, right = raw.split("->", 1)
                    elif ":" in raw:
                        left, right = raw.split(":", 1)
                    else:
                        left, right = raw, ""
                    frente = _clean_text(left, 140)
                    verso = _clean_text(right, 240)
                    tags = []
                    dificuldade = "medio"
                if not frente:
                    continue
                if not verso:
                    verso = "Explique o conceito com suas palavras."
                key = frente.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append({"frente": frente, "verso": verso, "tags": tags, "dificuldade": dificuldade})
                if len(out) >= max_items:
                    break
            return out

        def _as_question_suggestions(value: Any, max_items: int = 8) -> List[Dict]:
            if not isinstance(value, list):
                return []
            out: List[Dict] = []
            seen = set()
            for item in value:
                if isinstance(item, dict):
                    enunciado = _clean_text(item.get("enunciado") or item.get("pergunta") or item.get("question"), 220)
                    alternativas_raw = item.get("alternativas") or item.get("opcoes") or item.get("options") or []
                    if isinstance(alternativas_raw, str):
                        alternativas_raw = [x.strip() for x in re.split(r"\n|;", alternativas_raw) if x.strip()]
                    alternativas = _as_str_list(alternativas_raw, max_items=5, max_len=140)
                    if len(alternativas) < 2:
                        alternativas = [
                            "Alternativa A",
                            "Alternativa B",
                            "Alternativa C",
                            "Alternativa D",
                        ]
                    gabarito_raw = item.get("gabarito")
                    if gabarito_raw is None:
                        gabarito_raw = item.get("correta_index", item.get("indice_correto", 0))
                    if isinstance(gabarito_raw, str):
                        gr = gabarito_raw.strip().upper()
                        if gr in {"A", "B", "C", "D", "E"}:
                            gabarito = ["A", "B", "C", "D", "E"].index(gr)
                        else:
                            try:
                                gabarito = int(gr)
                            except Exception:
                                gabarito = 0
                    else:
                        try:
                            gabarito = int(gabarito_raw)
                        except Exception:
                            gabarito = 0
                    gabarito = max(0, min(gabarito, len(alternativas) - 1))
                    explicacao = _clean_text(item.get("explicacao") or item.get("resposta_curta") or item.get("feedback"), 240)
                    tags = _normalize_tags(item.get("tags"))
                    dificuldade = _normalize_dificuldade(item.get("dificuldade"))
                else:
                    raw = _clean_text(item, 320)
                    if "?" in raw:
                        enunciado = _clean_text(raw if raw.endswith("?") else raw.split("?")[0] + "?", 220)
                    else:
                        enunciado = _clean_text(raw, 220)
                    alternativas = [
                        "Alternativa A",
                        "Alternativa B",
                        "Alternativa C",
                        "Alternativa D",
                    ]
                    gabarito = 0
                    explicacao = ""
                    tags = []
                    dificuldade = "medio"
                if not enunciado:
                    continue
                key = enunciado.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    {
                        "enunciado": enunciado,
                        "alternativas": alternativas,
                        "gabarito": gabarito,
                        "explicacao": explicacao or "Use os pontos-chave do resumo para justificar a resposta correta.",
                        "tags": tags,
                        "dificuldade": dificuldade,
                    }
                )
                if len(out) >= max_items:
                    break
            return out

        def _normalize_summary_payload(data: Dict) -> Dict:
            titulo = _clean_text(data.get("titulo") or topic or "Resumo de estudo", 120)
            resumo_curto = _clean_text(data.get("resumo_curto") or data.get("resumo"), 520)
            resumo_estruturado = data.get("resumo_estruturado")
            if isinstance(resumo_estruturado, str):
                resumo_estruturado = [x.strip(" -") for x in resumo_estruturado.splitlines() if x.strip()]
            resumo_estruturado = _as_str_list(resumo_estruturado, max_items=10, max_len=220)
            topicos_principais = _as_str_list(data.get("topicos_principais") or data.get("topicos"), max_items=10, max_len=120)
            definicoes = _as_definition_list(data.get("definicoes"), max_items=8)
            exemplos = _as_str_list(data.get("exemplos"), max_items=8, max_len=220)
            pegadinhas = _as_str_list(data.get("pegadinhas"), max_items=8, max_len=220)
            checklist = _as_str_list(data.get("checklist_de_estudo"), max_items=10, max_len=180)
            sugestoes_flash = _as_flashcard_suggestions(data.get("sugestoes_flashcards"), max_items=10)
            sugestoes_q = _as_question_suggestions(data.get("sugestoes_questoes"), max_items=8)

            if not resumo_curto and resumo_estruturado:
                resumo_curto = " ".join(resumo_estruturado[:3])[:520]
            if not resumo_curto:
                resumo_curto = "Resumo indisponivel no momento."
            if not topicos_principais and definicoes:
                topicos_principais = [d.get("termo", "") for d in definicoes if d.get("termo")]
            if not topicos_principais:
                topicos_principais = ["Visao geral do material"]
            if not checklist:
                checklist = [
                    "Leia o resumo curto e marque duvidas",
                    "Resolva 5 questoes sobre os topicos principais",
                    "Revise os erros no mesmo dia",
                ]
            if not sugestoes_flash and topicos_principais:
                sugestoes_flash = [
                    {
                        "frente": f"O que e {topicos_principais[0]}?",
                        "verso": "Defina com suas palavras e cite um exemplo pratico.",
                        "tags": [topicos_principais[0]],
                        "dificuldade": "medio",
                    }
                ]
            if not sugestoes_q and topicos_principais:
                sugestoes_q = [
                    {
                        "enunciado": f"Qual alternativa melhor descreve {topicos_principais[0]}?",
                        "alternativas": [
                            "Definicao central do topico",
                            "Exemplo desconectado do tema",
                            "Opiniao sem relacao tecnica",
                            "Descricao incorreta do conceito",
                        ],
                        "gabarito": 0,
                        "explicacao": "A alternativa correta apresenta a definicao central do topico estudado.",
                        "tags": [topicos_principais[0]],
                        "dificuldade": "medio",
                    }
                ]

            return {
                "titulo": titulo,
                "resumo_curto": resumo_curto,
                "resumo_estruturado": resumo_estruturado,
                "topicos_principais": topicos_principais,
                "definicoes": definicoes,
                "exemplos": exemplos,
                "pegadinhas": pegadinhas,
                "checklist_de_estudo": checklist,
                "sugestoes_flashcards": sugestoes_flash,
                "sugestoes_questoes": sugestoes_q,
                # Compatibilidade com payload legado
                "resumo": resumo_curto,
                "topicos": topicos_principais,
            }

        if not content:
            return _normalize_summary_payload({})

        texto = "\n".join(content[:8])[:9000]
        prompt = f"""
Voce e um mentor de estudo para concursos e certificacoes tecnicas.
Gere um resumo acionavel em JSON.

Topico opcional: {topic}

Retorne APENAS JSON com este schema:
{{
  "titulo": "Titulo curto do material",
  "resumo_curto": "Resumo objetivo em ate 6 linhas",
  "resumo_estruturado": ["Item 1", "Item 2"],
  "topicos_principais": ["Topico 1", "Topico 2"],
  "definicoes": [{{"termo": "Termo", "definicao": "Definicao curta"}}],
  "exemplos": ["Exemplo pratico 1"],
  "pegadinhas": ["Erro comum 1"],
  "checklist_de_estudo": ["Acao 1", "Acao 2"],
  "sugestoes_flashcards": [{{"frente": "Pergunta", "verso": "Resposta", "tags": ["tag1"], "dificuldade": "medio"}}],
  "sugestoes_questoes": [{{"enunciado": "Pergunta objetiva", "alternativas": ["A", "B", "C", "D"], "gabarito": 0, "explicacao": "Motivo", "tags": ["tag1"], "dificuldade": "medio"}}]
}}

Material:
{texto}
"""
        tentativas = max(1, int(retries or 1))
        for attempt in range(tentativas):
            try:
                text = self._call_provider_text(prompt, "study_summary")
                if not text:
                    if self._should_abort_retry():
                        break
                    continue
                data = self.provider.extract_json_object(text)
                if isinstance(data, dict):
                    normalized = _normalize_summary_payload(data)
                    if normalized.get("resumo_curto") and self.validate_task_payload("study_summary", normalized)[0]:
                        return normalized
            except Exception:
                if self._should_abort_retry():
                    break
            if attempt < tentativas - 1:
                time.sleep(0.35)
        return _normalize_summary_payload({})


# ========== UTILIDADES ==========
def read_pdf(filepath: str) -> Optional[List[str]]:
    """LÃª PDF e retorna lista de textos"""
    try:
        from pypdf import PdfReader
        reader = PdfReader(filepath)
        texts = []
        for page in reader.pages:
            text = page.extract_text()
            if text and len(text) > 50:
                texts.append(text)
        return texts if texts else None
    except Exception as e:
        print(f"[PDF] Erro ao ler PDF: {e}")
        return None


# ========== TESTES ==========
if __name__ == "__main__":
    # Teste com Gemini
    try:
        provider = create_ai_provider("gemini", "YOUR_API_KEY_HERE")
        service = AIService(provider)
        
        quiz = service.generate_quiz(topic="Python bÃ¡sico", difficulty="MÃ©dio")
        if quiz:
            print("\n===== QUIZ GERADO =====")
            print(json.dumps(quiz, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"Erro no teste: {e}")

