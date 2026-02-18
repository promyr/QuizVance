# -*- coding: utf-8 -*-
"""
ServiÃ§o de AI Multi-Provider (Gemini + OpenAI)
Suporta Google Gemini e OpenAI GPT
"""

# -*- coding: utf-8 -*-
import json
import random
import time
import warnings
import sys
import os
import re
from typing import Optional, Dict, List, Any
from abc import ABC, abstractmethod

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
    
    def __init__(self, provider: AIProvider):
        self.provider = provider
    
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
                text = self.provider.generate_text(prompt)
                if not text:
                    if self._should_abort_retry():
                        break
                    continue

                data = self.provider.extract_json_list(text)
                if data is None:
                    data = self.provider.extract_json_object(text)

                normalizadas = self._normalize_quiz_batch_payload(data, quantidade)
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
                text = self.provider.generate_text(prompt)
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
                text = self.provider.generate_text(prompt)
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
                text = self.provider.generate_text(prompt)
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
                text = self.provider.generate_text(prompt)
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
                text = self.provider.generate_text(prompt)
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
                        result.append(
                            {
                                "dia": str(item.get("dia") or "Dia"),
                                "tema": str(item.get("tema") or "Geral"),
                                "atividade": str(item.get("atividade") or "Resolver questoes"),
                                "duracao_min": int(item.get("duracao_min") or tempo_diario_min),
                                "prioridade": int(item.get("prioridade") or 1),
                            }
                        )
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
        if not content:
            return {"resumo": "", "topicos": []}
        texto = "\n".join(content[:6])[:7000]
        prompt = f"""
Resuma o material para estudo.
Topico opcional: {topic}

Retorne APENAS JSON:
{{
  "resumo": "Resumo objetivo em ate 8 linhas.",
  "topicos": ["Topico 1", "Topico 2", "Topico 3", "Topico 4", "Topico 5"]
}}

Material:
{texto}
"""
        tentativas = max(1, int(retries or 1))
        for attempt in range(tentativas):
            try:
                text = self.provider.generate_text(prompt)
                if not text:
                    if self._should_abort_retry():
                        break
                    continue
                data = self.provider.extract_json_object(text)
                if isinstance(data, dict):
                    resumo = str(data.get("resumo") or "").strip()
                    topicos = data.get("topicos") or []
                    if not isinstance(topicos, list):
                        topicos = []
                    topicos = [str(t).strip() for t in topicos if str(t).strip()][:8]
                    if resumo:
                        return {"resumo": resumo, "topicos": topicos}
            except Exception:
                if self._should_abort_retry():
                    break
            if attempt < tentativas - 1:
                time.sleep(0.35)
        return {"resumo": "Resumo indisponivel no momento.", "topicos": []}


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

