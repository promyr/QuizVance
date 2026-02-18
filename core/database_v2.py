# -*- coding: utf-8 -*-
"""
Database V2.0 - Quiz Vance

Sistema de banco de dados SQLite com suporte a:
- AutenticaÃ§Ã£o tradicional e OAuth
- Multi-provider de IA
- Sistema de gamificaÃ§Ã£o completo
"""

import sqlite3
import datetime
import json
import hashlib
from typing import Optional, Dict, List, Tuple
from core.app_paths import ensure_runtime_dirs, get_db_path


class Database:
    """Gerenciador de banco de dados SQLite"""
    
    def __init__(self, db_path: Optional[str] = None):
        ensure_runtime_dirs()
        self.db_path = db_path or str(get_db_path())
    
    def conectar(self):
        """Cria conexÃ£o com banco"""
        return sqlite3.connect(self.db_path, check_same_thread=False)
    
    def iniciar_banco(self):
        """Cria todas as tabelas necessÃ¡rias"""
        conn = self.conectar()
        cursor = conn.cursor()
        
        # Tabela de usuÃ¡rios
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                senha TEXT NOT NULL,
                idade INTEGER,
                data_nascimento TEXT,
                avatar TEXT DEFAULT 'user',
                tema_escuro INTEGER DEFAULT 0,
                xp INTEGER DEFAULT 0,
                nivel TEXT DEFAULT 'Bronze',
                acertos INTEGER DEFAULT 0,
                total_questoes INTEGER DEFAULT 0,
                streak_dias INTEGER DEFAULT 0,
                ultima_atividade DATE,
                onboarding_seen INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._migrar_schema(cursor)
        
        # Tabela de configuraÃ§Ã£o de IA por usuÃ¡rio
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_ai_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                provider TEXT DEFAULT 'gemini',
                model TEXT DEFAULT 'gemini-2.5-flash',
                economia_mode INTEGER DEFAULT 0,
                api_key TEXT,
                FOREIGN KEY (user_id) REFERENCES usuarios (id),
                UNIQUE (user_id)
            )
        """)
        cursor.execute("PRAGMA table_info(user_ai_config)")
        ai_cols = {row[1] for row in cursor.fetchall()}
        if "economia_mode" not in ai_cols:
            cursor.execute("ALTER TABLE user_ai_config ADD COLUMN economia_mode INTEGER DEFAULT 0")
        
        # Tabela de OAuth
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS oauth_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                access_token TEXT,
                refresh_token TEXT,
                token_expires DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES usuarios (id),
                UNIQUE (provider, provider_id)
            )
        """)
        
        # Tabela de histÃ³rico de XP
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historico_xp (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                xp_ganho INTEGER NOT NULL,
                motivo TEXT,
                data_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES usuarios (id)
            )
        """)
        
        # Tabela de questÃµes erradas
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS questoes_erros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                dados_json TEXT NOT NULL,
                corrigido INTEGER DEFAULT 0,
                data_erro DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES usuarios (id)
            )
        """)
        
        # Tabela de conquistas
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conquistas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT UNIQUE NOT NULL,
                titulo TEXT NOT NULL,
                descricao TEXT,
                icone TEXT,
                xp_bonus INTEGER DEFAULT 0,
                criterio_tipo TEXT,
                criterio_valor INTEGER
            )
        """)
        
        # Tabela de conquistas do usuÃ¡rio
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuario_conquistas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                conquista_id INTEGER NOT NULL,
                data_conquista DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES usuarios (id),
                FOREIGN KEY (conquista_id) REFERENCES conquistas (id),
                UNIQUE (user_id, conquista_id)
            )
        """)
        
        # Tabela de tempo de estudo
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS estudo_tempo_diario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                materia TEXT NOT NULL,
                dia DATE NOT NULL,
                segundos_estudo INTEGER DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES usuarios (id),
                UNIQUE (user_id, materia, dia)
            )
        """)
        
        # Tabela de biblioteca de PDFs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS biblioteca_pdfs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                nome_arquivo TEXT NOT NULL,
                caminho_arquivo TEXT NOT NULL,
                categoria TEXT DEFAULT 'Geral',
                total_paginas INTEGER DEFAULT 0,
                data_upload DATETIME DEFAULT CURRENT_TIMESTAMP,
                ultimo_uso DATETIME,
                vezes_usado INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES usuarios (id)
            )
        """)
        
        # Tabela de cache de questÃµes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS banco_questoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tema TEXT NOT NULL,
                dificuldade TEXT NOT NULL,
                dados_json TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS questoes_usuario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                qhash TEXT NOT NULL,
                dados_json TEXT NOT NULL,
                tema TEXT DEFAULT 'Geral',
                dificuldade TEXT DEFAULT 'intermediario',
                favorita INTEGER DEFAULT 0,
                marcado_erro INTEGER DEFAULT 0,
                tentativas INTEGER DEFAULT 0,
                acertos INTEGER DEFAULT 0,
                erros INTEGER DEFAULT 0,
                revisao_nivel INTEGER DEFAULT 0,
                proxima_revisao DATETIME,
                ultima_pratica DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES usuarios (id),
                UNIQUE (user_id, qhash)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quiz_filtros_salvos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                nome TEXT NOT NULL,
                filtro_json TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES usuarios (id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS study_plan_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                objetivo TEXT,
                data_prova TEXT,
                tempo_diario_min INTEGER DEFAULT 90,
                status TEXT DEFAULT 'ativo',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES usuarios (id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS study_plan_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                dia TEXT NOT NULL,
                tema TEXT NOT NULL,
                atividade TEXT NOT NULL,
                duracao_min INTEGER DEFAULT 60,
                prioridade INTEGER DEFAULT 1,
                concluido INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (plan_id) REFERENCES study_plan_runs (id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS study_packages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                titulo TEXT NOT NULL,
                source_nome TEXT,
                dados_json TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES usuarios (id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS questoes_notas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                qhash TEXT NOT NULL,
                nota TEXT DEFAULT '',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES usuarios (id),
                UNIQUE (user_id, qhash)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS estudo_progresso_diario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                dia DATE NOT NULL,
                questoes_respondidas INTEGER DEFAULT 0,
                acertos INTEGER DEFAULT 0,
                flashcards_revisados INTEGER DEFAULT 0,
                discursivas_corrigidas INTEGER DEFAULT 0,
                tempo_segundos INTEGER DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES usuarios (id),
                UNIQUE (user_id, dia)
            )
        """)

        # Monetizacao / assinatura
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_subscription (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                plan_code TEXT DEFAULT 'free',
                premium_until DATETIME,
                trial_used INTEGER DEFAULT 0,
                trial_started_at DATETIME,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES usuarios (id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usage_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                feature_key TEXT NOT NULL,
                day_key DATE NOT NULL,
                used_count INTEGER DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES usuarios (id),
                UNIQUE (user_id, feature_key, day_key)
            )
        """)
        
        conn.commit()
        conn.close()
        
        # Popular conquistas padrÃ£o
        self._popular_conquistas()
        self._garantir_admin_padrao()

    def _migrar_schema(self, cursor):
        """Aplica migracoes em bancos antigos sem perder dados."""
        cursor.execute("PRAGMA table_info(usuarios)")
        colunas = {row[1] for row in cursor.fetchall()}
        if "data_nascimento" not in colunas:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN data_nascimento TEXT")
        if "meta_questoes_diaria" not in colunas:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN meta_questoes_diaria INTEGER DEFAULT 20")
        if "onboarding_seen" not in colunas:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN onboarding_seen INTEGER DEFAULT 1")
        cursor.execute("PRAGMA table_info(questoes_usuario)")
        q_cols = {row[1] for row in cursor.fetchall()}
        if q_cols:
            if "revisao_nivel" not in q_cols:
                cursor.execute("ALTER TABLE questoes_usuario ADD COLUMN revisao_nivel INTEGER DEFAULT 0")
            if "proxima_revisao" not in q_cols:
                cursor.execute("ALTER TABLE questoes_usuario ADD COLUMN proxima_revisao DATETIME")
    
    def _popular_conquistas(self):
        """Popula conquistas padrÃ£o se nÃ£o existirem"""
        from config import CONQUISTAS
        
        conn = self.conectar()
        cursor = conn.cursor()
        
        for conquista in CONQUISTAS:
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO conquistas 
                    (codigo, titulo, descricao, icone, xp_bonus, criterio_tipo, criterio_valor)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    conquista['codigo'],
                    conquista['titulo'],
                    conquista['descricao'],
                    conquista['icone'],
                    conquista['xp_bonus'],
                    conquista['criterio_tipo'],
                    conquista['criterio_valor']
                ))
            except Exception:
                pass
        
        conn.commit()
        conn.close()

    def _garantir_admin_padrao(self):
        """Cria usuario administrador padrao se nao existir."""
        conn = self.conectar()
        cursor = conn.cursor()
        try:
            senha_hash = hashlib.sha256("admin".encode()).hexdigest()
            cursor.execute(
                """
                INSERT OR IGNORE INTO usuarios
                (nome, email, senha, idade, nivel, xp, ultima_atividade, onboarding_seen)
                VALUES (?, ?, ?, ?, ?, ?, DATE('now'), 1)
                """,
                ("admin", "admin@local", senha_hash, 18, "Administrador", 99999),
            )
            cursor.execute(
                """
                INSERT OR IGNORE INTO user_subscription
                (user_id, plan_code, premium_until, trial_used, trial_started_at, updated_at)
                SELECT id, 'premium_30', DATETIME('now', '+3650 days'), 1, DATETIME('now'), CURRENT_TIMESTAMP
                FROM usuarios
                WHERE email = 'admin@local'
                """
            )
            conn.commit()
        finally:
            conn.close()

    def atualizar_tema_escuro(self, user_id: int, tema_escuro: bool):
        """Atualiza preferencia de tema do usuario."""
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE usuarios SET tema_escuro = ? WHERE id = ?",
            (1 if tema_escuro else 0, user_id),
        )
        conn.commit()
        conn.close()

    def marcar_onboarding_visto(self, user_id: int):
        """Marca a tela de boas-vindas como concluida para o usuario."""
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE usuarios SET onboarding_seen = 1 WHERE id = ?",
            (user_id,),
        )
        conn.commit()
        conn.close()

    def criar_conta(self, nome: str, identificador: str, senha: str, data_nascimento: str) -> Tuple[bool, str]:
        """Cria nova conta usando ID e data de nascimento."""
        conn = self.conectar()
        cursor = conn.cursor()
        
        try:
            email = (identificador or "").strip().lower()
            nome = (nome or "").strip()
            senha = senha or ""
            data_nascimento = (data_nascimento or "").strip()

            # Verificar se email jÃ¡ existe
            cursor.execute("SELECT id FROM usuarios WHERE email = ?", (email,))
            if cursor.fetchone():
                conn.close()
                return False, "ID ja cadastrado"
            
            # Hash da senha (em produÃ§Ã£o, use bcrypt!)
            senha_hash = hashlib.sha256(senha.encode()).hexdigest()
            
            # Inserir usuÃ¡rio
            cursor.execute("""
                INSERT INTO usuarios (nome, email, senha, idade, data_nascimento, ultima_atividade, onboarding_seen)
                VALUES (?, ?, ?, ?, ?, DATE('now'), 0)
            """, (nome, email, senha_hash, self._calcular_idade(data_nascimento), data_nascimento))
            
            user_id = cursor.lastrowid
            
            # Criar configuraÃ§Ã£o de IA padrÃ£o
            cursor.execute("""
                INSERT INTO user_ai_config (user_id, provider, model)
                VALUES (?, 'gemini', 'gemini-2.5-flash')
            """, (user_id,))

            # Trial de premium por 1 dia para novos usuarios
            cursor.execute(
                """
                INSERT INTO user_subscription
                (user_id, plan_code, premium_until, trial_used, trial_started_at, updated_at)
                VALUES (?, 'trial', DATETIME('now', '+1 day'), 1, DATETIME('now'), CURRENT_TIMESTAMP)
                """,
                (user_id,),
            )
            
            conn.commit()
            conn.close()
            return True, "Conta criada com sucesso!"
            
        except Exception as e:
            conn.close()
            return False, f"Erro ao criar conta: {str(e)}"
    
    def fazer_login(self, identificador: str, senha: str) -> Optional[Dict]:
        """Login tradicional com ID e senha."""
        conn = self.conectar()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        email = (identificador or "").strip().lower()
        senha = senha or ""
        senha_hash = hashlib.sha256(senha.encode()).hexdigest()
        
        # 1) Prioridade absoluta: ID definido pelo usuario (campo email no schema atual)
        cursor.execute("""
            SELECT u.*, 
                   ai.provider, ai.model, ai.api_key, ai.economia_mode
            FROM usuarios u
            LEFT JOIN user_ai_config ai ON u.id = ai.user_id
            WHERE lower(u.email) = ? AND u.senha = ?
        """, (email, senha_hash))
        
        row = cursor.fetchone()
        
        if row:
            row_dict = dict(row)
            row_dict["oauth_google"] = 0
            row_dict.update(self.get_subscription_status(int(row_dict["id"])))
            conn.close()
            return row_dict

        # 2) Fallback: ID curto (parte antes do @ do email)
        if "@" not in email:
            cursor.execute("""
                SELECT u.*,
                       ai.provider, ai.model, ai.api_key, ai.economia_mode
                FROM usuarios u
                LEFT JOIN user_ai_config ai ON u.id = ai.user_id
                WHERE lower(u.email) LIKE ? AND u.senha = ?
            """, (f"{email}@%", senha_hash))
            row_short = cursor.fetchone()
            if row_short:
                row_dict = dict(row_short)
                row_dict["oauth_google"] = 0
                row_dict.update(self.get_subscription_status(int(row_dict["id"])))
                conn.close()
                return row_dict

        # 3) Fallback opcional: login por nome
        cursor.execute("""
            SELECT u.*,
                   ai.provider, ai.model, ai.api_key, ai.economia_mode
            FROM usuarios u
            LEFT JOIN user_ai_config ai ON u.id = ai.user_id
            WHERE lower(u.nome) = ? AND u.senha = ?
        """, (email, senha_hash))
        row_name = cursor.fetchone()
        if row_name:
            row_dict = dict(row_name)
            row_dict["oauth_google"] = 0
            row_dict.update(self.get_subscription_status(int(row_dict["id"])))
            conn.close()
            return row_dict

        # Compatibilidade com dados legados: senha em texto puro.
        cursor.execute("""
            SELECT u.*,
                   ai.provider, ai.model, ai.api_key, ai.economia_mode
            FROM usuarios u
            LEFT JOIN user_ai_config ai ON u.id = ai.user_id
            WHERE lower(u.email) = ? AND u.senha = ?
        """, (email, senha))
        row_plain = cursor.fetchone()
        if row_plain:
            cursor.execute(
                "UPDATE usuarios SET senha = ? WHERE id = ?",
                (senha_hash, row_plain["id"])
            )
            conn.commit()
            row_dict = dict(row_plain)
            row_dict["oauth_google"] = 0
            row_dict.update(self.get_subscription_status(int(row_dict["id"])))
            conn.close()
            return row_dict

        # Compatibilidade legada + ID curto
        if "@" not in email:
            cursor.execute("""
                SELECT u.*,
                       ai.provider, ai.model, ai.api_key, ai.economia_mode
                FROM usuarios u
                LEFT JOIN user_ai_config ai ON u.id = ai.user_id
                WHERE lower(u.email) LIKE ? AND u.senha = ?
            """, (f"{email}@%", senha))
            row_plain_short = cursor.fetchone()
            if row_plain_short:
                cursor.execute(
                    "UPDATE usuarios SET senha = ? WHERE id = ?",
                    (senha_hash, row_plain_short["id"])
                )
                conn.commit()
                row_dict = dict(row_plain_short)
                row_dict["oauth_google"] = 0
                row_dict.update(self.get_subscription_status(int(row_dict["id"])))
                conn.close()
                return row_dict

        # Compatibilidade legada + nome
        cursor.execute("""
            SELECT u.*,
                   ai.provider, ai.model, ai.api_key, ai.economia_mode
            FROM usuarios u
            LEFT JOIN user_ai_config ai ON u.id = ai.user_id
            WHERE lower(u.nome) = ? AND u.senha = ?
        """, (email, senha))
        row_plain_name = cursor.fetchone()
        if row_plain_name:
            cursor.execute(
                "UPDATE usuarios SET senha = ? WHERE id = ?",
                (senha_hash, row_plain_name["id"])
            )
            conn.commit()
            row_dict = dict(row_plain_name)
            row_dict["oauth_google"] = 0
            row_dict.update(self.get_subscription_status(int(row_dict["id"])))
            conn.close()
            return row_dict

        conn.close()
        return None

    def _calcular_idade(self, data_nascimento: str) -> Optional[int]:
        """Calcula idade aproximada para manter compatibilidade do campo legado."""
        try:
            dt_nasc = datetime.datetime.strptime(data_nascimento, "%d/%m/%Y").date()
            hoje = datetime.date.today()
            return hoje.year - dt_nasc.year - ((hoje.month, hoje.day) < (dt_nasc.month, dt_nasc.day))
        except Exception:
            return None

    def contar_usuarios(self) -> int:
        """Retorna quantidade total de usuÃ¡rios cadastrados."""
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM usuarios")
        total = cursor.fetchone()[0]
        conn.close()
        return int(total or 0)
    
    def fazer_login_oauth(
        self,
        email: str,
        nome: str,
        google_id: str,
        avatar_url: str = None
    ) -> Optional[Dict]:
        """Login ou cadastro via Google OAuth"""
        conn = self.conectar()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        email = (email or "").strip().lower()
        nome = (nome or "").strip()
        
        # Verificar se usuÃ¡rio existe
        cursor.execute("SELECT id FROM usuarios WHERE email = ?", (email,))
        row = cursor.fetchone()
        
        if row:
            user_id = row['id']
        else:
            # Criar novo usuÃ¡rio
            senha_random = hashlib.sha256(google_id.encode()).hexdigest()
            cursor.execute("""
                INSERT INTO usuarios (nome, email, senha, idade, avatar, ultima_atividade, onboarding_seen)
                VALUES (?, ?, ?, ?, ?, DATE('now'), 0)
            """, (nome, email, senha_random, 18, avatar_url or 'user'))
            
            user_id = cursor.lastrowid
            
            # Criar configuraÃ§Ã£o de IA
            cursor.execute("""
                INSERT INTO user_ai_config (user_id)
                VALUES (?)
            """, (user_id,))
            cursor.execute(
                """
                INSERT INTO user_subscription
                (user_id, plan_code, premium_until, trial_used, trial_started_at, updated_at)
                VALUES (?, 'trial', DATETIME('now', '+1 day'), 1, DATETIME('now'), CURRENT_TIMESTAMP)
                """,
                (user_id,),
            )
        
        # Salvar/atualizar OAuth info
        cursor.execute("""
            INSERT OR REPLACE INTO oauth_users (user_id, provider, provider_id)
            VALUES (?, 'google', ?)
        """, (user_id, google_id))
        
        conn.commit()
        
        # Retornar dados do usuÃ¡rio
        cursor.execute("""
            SELECT u.*, 
                   ai.provider, ai.model, ai.api_key, ai.economia_mode
            FROM usuarios u
            LEFT JOIN user_ai_config ai ON u.id = ai.user_id
            WHERE u.id = ?
        """, (user_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            row_dict = dict(row)
            row_dict["oauth_google"] = 1
            row_dict.update(self.get_subscription_status(int(row_dict["id"])))
            return row_dict
        return None

    def _ensure_subscription_row(self, cursor, user_id: int):
        cursor.execute(
            """
            INSERT OR IGNORE INTO user_subscription
            (user_id, plan_code, premium_until, trial_used, trial_started_at, updated_at)
            VALUES (?, 'free', NULL, 0, NULL, CURRENT_TIMESTAMP)
            """,
            (user_id,),
        )

    def get_subscription_status(self, user_id: int) -> Dict:
        conn = self.conectar()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        self._ensure_subscription_row(cursor, user_id)
        conn.commit()
        cursor.execute(
            """
            SELECT plan_code, premium_until, trial_used, trial_started_at
            FROM user_subscription
            WHERE user_id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return {
                "plan_code": "free",
                "premium_active": 0,
                "premium_until": None,
                "trial_used": 0,
            }
        premium_until = row["premium_until"]
        premium_active = 0
        if premium_until:
            try:
                dt = datetime.datetime.strptime(str(premium_until), "%Y-%m-%d %H:%M:%S")
                premium_active = 1 if dt > datetime.datetime.now() else 0
            except Exception:
                premium_active = 0
        return {
            "plan_code": row["plan_code"] or "free",
            "premium_active": int(premium_active),
            "premium_until": premium_until,
            "trial_used": int(row["trial_used"] or 0),
        }

    def ativar_plano_premium(self, user_id: int, plano: str) -> Tuple[bool, str]:
        dias = 15 if plano == "premium_15" else 30 if plano == "premium_30" else 0
        if dias <= 0:
            return False, "Plano invalido."
        conn = self.conectar()
        cursor = conn.cursor()
        try:
            self._ensure_subscription_row(cursor, user_id)
            cursor.execute(
                """
                UPDATE user_subscription
                SET plan_code = ?,
                    premium_until = CASE
                        WHEN premium_until IS NOT NULL AND DATETIME(premium_until) > DATETIME('now')
                            THEN DATETIME(premium_until, '+' || ? || ' days')
                        ELSE DATETIME('now', '+' || ? || ' days')
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (plano, dias, dias, user_id),
            )
            conn.commit()
            return True, "Plano ativado com sucesso."
        except Exception as ex:
            return False, f"Falha ao ativar plano: {ex}"
        finally:
            conn.close()

    def consumir_limite_diario(self, user_id: int, feature_key: str, limite: int) -> Tuple[bool, int]:
        if limite <= 0:
            return True, 0
        conn = self.conectar()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO usage_daily (user_id, feature_key, day_key, used_count, updated_at)
                VALUES (?, ?, DATE('now'), 0, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, feature_key, day_key) DO NOTHING
                """,
                (user_id, feature_key),
            )
            cursor.execute(
                """
                SELECT used_count
                FROM usage_daily
                WHERE user_id = ? AND feature_key = ? AND day_key = DATE('now')
                """,
                (user_id, feature_key),
            )
            row = cursor.fetchone()
            used = int((row[0] if row else 0) or 0)
            if used >= limite:
                conn.commit()
                return False, used
            cursor.execute(
                """
                UPDATE usage_daily
                SET used_count = used_count + 1, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND feature_key = ? AND day_key = DATE('now')
                """,
                (user_id, feature_key),
            )
            conn.commit()
            return True, used + 1
        finally:
            conn.close()
    
    def atualizar_api_key(self, user_id: int, api_key: str):
        """Atualiza API key do usuÃ¡rio"""
        conn = self.conectar()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE user_ai_config
            SET api_key = ?
            WHERE user_id = ?
        """, (api_key, user_id))
        
        conn.commit()
        conn.close()
    
    def atualizar_provider_ia(self, user_id: int, provider: str, model: str):
        """Atualiza configuraÃ§Ã£o de IA do usuÃ¡rio"""
        conn = self.conectar()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE user_ai_config
            SET provider = ?, model = ?
            WHERE user_id = ?
        """, (provider, model, user_id))
        
        conn.commit()
        conn.close()
    
    def registrar_ganho_xp(self, user_id: int, xp: int, motivo: str = ""):
        """Registra ganho de XP"""
        conn = self.conectar()
        cursor = conn.cursor()
        
        # Inserir no histÃ³rico
        cursor.execute("""
            INSERT INTO historico_xp (user_id, xp_ganho, motivo)
            VALUES (?, ?, ?)
        """, (user_id, xp, motivo))
        
        # Atualizar XP total
        cursor.execute("""
            UPDATE usuarios
            SET xp = xp + ?,
                ultima_atividade = DATE('now')
            WHERE id = ?
        """, (xp, user_id))
        
        conn.commit()
        conn.close()

    def registrar_resultado_quiz(self, user_id: int, acertos: int, total: int, xp: int):
        """Atualiza estatisticas de quiz e XP."""
        conn = self.conectar()
        cursor = conn.cursor()
        novo_streak = self._calcular_streak(cursor, user_id)
        cursor.execute("""
            UPDATE usuarios
            SET xp = xp + ?,
                acertos = acertos + ?,
                total_questoes = total_questoes + ?,
                streak_dias = ?,
                ultima_atividade = DATE('now')
            WHERE id = ?
        """, (xp, acertos, total, novo_streak, user_id))
        cursor.execute(
            """
            INSERT INTO historico_xp (user_id, xp_ganho, motivo)
            VALUES (?, ?, ?)
            """,
            (user_id, xp, f"Quiz {acertos}/{total}"),
        )
        self._registrar_progresso_diario_cursor(
            cursor,
            user_id,
            questoes=max(0, int(total or 0)),
            acertos=max(0, int(acertos or 0)),
        )
        conn.commit()
        conn.close()

    def atualizar_identificador(self, user_id: int, novo_identificador: str) -> Tuple[bool, str]:
        """Atualiza o ID (campo email) do usuario com validacao de unicidade."""
        conn = self.conectar()
        cursor = conn.cursor()
        try:
            novo_id = (novo_identificador or "").strip().lower()
            if not novo_id:
                return False, "ID nao pode ficar vazio."

            cursor.execute(
                "SELECT id FROM usuarios WHERE lower(email) = ? AND id <> ?",
                (novo_id, user_id),
            )
            if cursor.fetchone():
                return False, "Este ID ja esta em uso por outra conta."

            cursor.execute(
                "UPDATE usuarios SET email = ? WHERE id = ?",
                (novo_id, user_id),
            )
            if cursor.rowcount == 0:
                return False, "Usuario nao encontrado."

            conn.commit()
            return True, "ID atualizado com sucesso."
        except Exception as ex:
            return False, f"Erro ao atualizar ID: {str(ex)}"
        finally:
            conn.close()

    def atualizar_economia_ia(self, user_id: int, economia_mode: bool):
        """Atualiza modo economia da IA do usuario."""
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE user_ai_config
            SET economia_mode = ?
            WHERE user_id = ?
            """,
            (1 if economia_mode else 0, user_id),
        )
        conn.commit()
        conn.close()

    def _calcular_streak(self, cursor, user_id: int) -> int:
        cursor.execute(
            "SELECT streak_dias, ultima_atividade FROM usuarios WHERE id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            return 1
        streak_atual = int(row[0] or 0)
        ultima = row[1]
        hoje = datetime.date.today()
        if not ultima:
            return max(1, streak_atual)
        try:
            ultima_data = datetime.datetime.strptime(str(ultima), "%Y-%m-%d").date()
        except ValueError:
            return max(1, streak_atual)
        if ultima_data == hoje:
            return max(1, streak_atual)
        if ultima_data == (hoje - datetime.timedelta(days=1)):
            return max(1, streak_atual + 1)
        return 1

    def _registrar_progresso_diario_cursor(
        self,
        cursor,
        user_id: int,
        questoes: int = 0,
        acertos: int = 0,
        flashcards: int = 0,
        discursivas: int = 0,
        tempo_segundos: int = 0,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO estudo_progresso_diario
                (user_id, dia, questoes_respondidas, acertos, flashcards_revisados, discursivas_corrigidas, tempo_segundos, updated_at)
            VALUES (?, DATE('now'), ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, dia) DO UPDATE SET
                questoes_respondidas = estudo_progresso_diario.questoes_respondidas + excluded.questoes_respondidas,
                acertos = estudo_progresso_diario.acertos + excluded.acertos,
                flashcards_revisados = estudo_progresso_diario.flashcards_revisados + excluded.flashcards_revisados,
                discursivas_corrigidas = estudo_progresso_diario.discursivas_corrigidas + excluded.discursivas_corrigidas,
                tempo_segundos = estudo_progresso_diario.tempo_segundos + excluded.tempo_segundos,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                user_id,
                max(0, int(questoes or 0)),
                max(0, int(acertos or 0)),
                max(0, int(flashcards or 0)),
                max(0, int(discursivas or 0)),
                max(0, int(tempo_segundos or 0)),
            ),
        )

    def registrar_progresso_diario(
        self,
        user_id: int,
        questoes: int = 0,
        acertos: int = 0,
        flashcards: int = 0,
        discursivas: int = 0,
        tempo_segundos: int = 0,
    ) -> None:
        conn = self.conectar()
        cursor = conn.cursor()
        self._registrar_progresso_diario_cursor(
            cursor,
            user_id,
            questoes=questoes,
            acertos=acertos,
            flashcards=flashcards,
            discursivas=discursivas,
            tempo_segundos=tempo_segundos,
        )
        novo_streak = self._calcular_streak(cursor, user_id)
        cursor.execute(
            """
            UPDATE usuarios
            SET streak_dias = ?, ultima_atividade = DATE('now')
            WHERE id = ?
            """,
            (novo_streak, user_id),
        )
        conn.commit()
        conn.close()

    def obter_progresso_diario(self, user_id: int) -> Dict:
        conn = self.conectar()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT meta_questoes_diaria, streak_dias
            FROM usuarios
            WHERE id = ?
            """,
            (user_id,),
        )
        user_row = cursor.fetchone()
        meta = int((user_row["meta_questoes_diaria"] if user_row else 20) or 20)
        streak = int((user_row["streak_dias"] if user_row else 0) or 0)
        cursor.execute(
            """
            SELECT questoes_respondidas, acertos, flashcards_revisados, discursivas_corrigidas, tempo_segundos
            FROM estudo_progresso_diario
            WHERE user_id = ? AND dia = DATE('now')
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        conn.close()
        feitos = int((row["questoes_respondidas"] if row else 0) or 0)
        acertos = int((row["acertos"] if row else 0) or 0)
        return {
            "meta_questoes": max(5, meta),
            "questoes_respondidas": feitos,
            "acertos": acertos,
            "flashcards_revisados": int((row["flashcards_revisados"] if row else 0) or 0),
            "discursivas_corrigidas": int((row["discursivas_corrigidas"] if row else 0) or 0),
            "tempo_segundos": int((row["tempo_segundos"] if row else 0) or 0),
            "progresso_meta": min(1.0, feitos / max(1, meta)),
            "streak_dias": streak,
        }
    
    def obter_dados_grafico(self, user_id: int, dias: int = 7) -> Tuple[List[Dict], int]:
        """ObtÃ©m dados para grÃ¡fico de XP"""
        conn = self.conectar()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DATE(data_hora) as dia, SUM(xp_ganho) as xp
            FROM historico_xp
            WHERE user_id = ? AND data_hora >= DATE('now', '-' || ? || ' days')
            GROUP BY DATE(data_hora)
            ORDER BY dia ASC
        """, (user_id, dias))
        
        resultados = cursor.fetchall()
        conn.close()
        
        # Preencher todos os dias
        dados = []
        total_xp = 0
        hoje = datetime.date.today()
        
        data_dict = {r[0]: r[1] for r in resultados}
        
        for i in range(dias - 1, -1, -1):
            dia = (hoje - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            xp = data_dict.get(dia, 0)
            total_xp += xp
            
            # Label do dia
            if dias <= 7:
                label = ["Seg", "Ter", "Qua", "Qui", "Sex", "SÃ¡b", "Dom"][
                    datetime.datetime.strptime(dia, "%Y-%m-%d").weekday()
                ]
            else:
                label = f"{dia.split('-')[2]}/{dia.split('-')[1]}"
            
            dados.append({"dia": label, "xp": xp})
        
        return dados, total_xp
    
    # Adicionar mais mÃ©todos conforme necessÃ¡rio...
    
    def obter_ranking(self, periodo: str = "Geral") -> List[Dict]:
        """ObtÃ©m ranking de usuÃ¡rios"""
        conn = self.conectar()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if periodo == "Hoje":
            cursor.execute("""
                SELECT u.nome, u.avatar, u.nivel, u.xp, u.acertos, u.total_questoes
                FROM usuarios u
                WHERE u.ultima_atividade = DATE('now')
                ORDER BY u.xp DESC
                LIMIT 50
            """)
        else:
            cursor.execute("""
                SELECT u.nome, u.avatar, u.nivel, u.xp, u.acertos, u.total_questoes
                FROM usuarios u
                ORDER BY u.xp DESC
                LIMIT 50
            """)
        
        rows = cursor.fetchall()
        conn.close()
        
        ranking = []
        for row in rows:
            user_dict = dict(row)
            # Calcular mÃ©tricas
            total = user_dict['total_questoes']
            acertos = user_dict['acertos']
            user_dict['taxa_acerto'] = (acertos / total * 100) if total > 0 else 0
            user_dict['horas_estudo'] = 0  # TODO: calcular do banco
            user_dict['pontuacao'] = user_dict['xp']
            ranking.append(user_dict)
        
        return ranking

    def _question_hash(self, question: Dict) -> str:
        base = {
            "enunciado": question.get("enunciado", ""),
            "alternativas": question.get("alternativas", []),
            "correta_index": question.get("correta_index", question.get("correta", 0)),
        }
        payload = json.dumps(base, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def salvar_questao_cache(self, tema: str, dificuldade: str, questao: Dict) -> None:
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO banco_questoes (tema, dificuldade, dados_json)
            VALUES (?, ?, ?)
            """,
            (
                str((tema or "Geral").strip() or "Geral"),
                str((dificuldade or "intermediario").strip() or "intermediario"),
                json.dumps(questao, ensure_ascii=False),
            ),
        )
        conn.commit()
        conn.close()

    def listar_questoes_cache(self, tema: str, dificuldade: str, limite: int = 10) -> List[Dict]:
        conn = self.conectar()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT dados_json
            FROM banco_questoes
            WHERE lower(tema) = lower(?)
              AND lower(dificuldade) = lower(?)
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (
                str((tema or "Geral").strip() or "Geral"),
                str((dificuldade or "intermediario").strip() or "intermediario"),
                int(max(1, limite)),
            ),
        )
        rows = cursor.fetchall()
        conn.close()
        out = []
        for row in rows:
            try:
                out.append(json.loads(row["dados_json"] or "{}"))
            except Exception:
                continue
        return out

    def registrar_questao_usuario(
        self,
        user_id: int,
        question: Dict,
        tema: str = "Geral",
        dificuldade: str = "intermediario",
        tentativa_correta: Optional[bool] = None,
        favorita: Optional[bool] = None,
        marcado_erro: Optional[bool] = None,
    ) -> None:
        conn = self.conectar()
        cursor = conn.cursor()
        try:
            qhash = self._question_hash(question)
            cursor.execute(
                """
                SELECT favorita, marcado_erro, tentativas, acertos, erros, revisao_nivel
                FROM questoes_usuario
                WHERE user_id = ? AND qhash = ?
                """,
                (user_id, qhash),
            )
            row = cursor.fetchone()

            fav = int(bool(favorita)) if favorita is not None else (row[0] if row else 0)
            mark = int(bool(marcado_erro)) if marcado_erro is not None else (row[1] if row else 0)
            tentativas = row[2] if row else 0
            acertos = row[3] if row else 0
            erros = row[4] if row else 0
            revisao_nivel = row[5] if row else 0
            proxima_revisao_expr = None

            if tentativa_correta is True:
                tentativas += 1
                acertos += 1
                mark = 0
                revisao_nivel = min(4, int(revisao_nivel or 0) + 1)
                dias_map = [1, 3, 7, 14, 30]
                dias = dias_map[revisao_nivel]
                proxima_revisao_expr = f"DATETIME('now', '+{dias} days')"
            elif tentativa_correta is False:
                tentativas += 1
                erros += 1
                revisao_nivel = 0
                mark = 1
                proxima_revisao_expr = "DATETIME('now', '+1 day')"

            proxima_revisao_sql = proxima_revisao_expr or "NULL"

            cursor.execute(
                f"""
                INSERT INTO questoes_usuario
                (user_id, qhash, dados_json, tema, dificuldade, favorita, marcado_erro, tentativas, acertos, erros, revisao_nivel, proxima_revisao, ultima_pratica)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, {proxima_revisao_sql}, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, qhash) DO UPDATE SET
                    dados_json = excluded.dados_json,
                    tema = excluded.tema,
                    dificuldade = excluded.dificuldade,
                    favorita = excluded.favorita,
                    marcado_erro = excluded.marcado_erro,
                    tentativas = excluded.tentativas,
                    acertos = excluded.acertos,
                    erros = excluded.erros,
                    revisao_nivel = excluded.revisao_nivel,
                    proxima_revisao = COALESCE(excluded.proxima_revisao, questoes_usuario.proxima_revisao),
                    ultima_pratica = CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    qhash,
                    json.dumps(question, ensure_ascii=False),
                    tema or "Geral",
                    dificuldade or "intermediario",
                    fav,
                    mark,
                    tentativas,
                    acertos,
                    erros,
                    revisao_nivel,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def listar_questoes_usuario(self, user_id: int, modo: str = "all", limite: int = 20) -> List[Dict]:
        conn = self.conectar()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        where = "user_id = ?"
        if modo == "favoritas":
            where += " AND favorita = 1"
        elif modo == "erradas":
            where += " AND (marcado_erro = 1 OR erros > acertos)"
        elif modo == "nao_resolvidas":
            where += " AND tentativas = 0"

        order_by = "ultima_pratica DESC"
        if modo == "erradas":
            order_by = "CASE WHEN proxima_revisao IS NULL THEN 1 WHEN DATETIME(proxima_revisao) <= DATETIME('now') THEN 0 ELSE 1 END, DATETIME(proxima_revisao) ASC, ultima_pratica DESC"

        cursor.execute(
            f"""
            SELECT dados_json, tema, dificuldade, favorita, marcado_erro, tentativas, acertos, erros, revisao_nivel, proxima_revisao
            FROM questoes_usuario
            WHERE {where}
            ORDER BY {order_by}
            LIMIT ?
            """,
            (user_id, int(max(1, limite))),
        )
        rows = cursor.fetchall()
        conn.close()

        result = []
        for row in rows:
            try:
                q = json.loads(row["dados_json"] or "{}")
            except Exception:
                continue
            q["_meta"] = {
                "tema": row["tema"],
                "dificuldade": row["dificuldade"],
                "favorita": bool(row["favorita"]),
                "marcado_erro": bool(row["marcado_erro"]),
                "tentativas": int(row["tentativas"] or 0),
                "acertos": int(row["acertos"] or 0),
                "erros": int(row["erros"] or 0),
                "revisao_nivel": int(row["revisao_nivel"] or 0),
                "proxima_revisao": row["proxima_revisao"],
            }
            result.append(q)
        return result

    def salvar_filtro_quiz(self, user_id: int, nome: str, filtro: Dict) -> None:
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO quiz_filtros_salvos (user_id, nome, filtro_json)
            VALUES (?, ?, ?)
            """,
            (user_id, nome, json.dumps(filtro, ensure_ascii=False)),
        )
        conn.commit()
        conn.close()

    def atualizar_meta_diaria(self, user_id: int, meta_questoes: int):
        """Atualiza meta diaria de questoes do usuario."""
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE usuarios SET meta_questoes_diaria = ? WHERE id = ?",
            (int(max(5, min(200, meta_questoes))), user_id),
        )
        conn.commit()
        conn.close()

    def listar_filtros_quiz(self, user_id: int) -> List[Dict]:
        conn = self.conectar()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, nome, filtro_json, created_at
            FROM quiz_filtros_salvos
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        out = []
        for row in rows:
            try:
                filtro = json.loads(row["filtro_json"] or "{}")
            except Exception:
                filtro = {}
            out.append({"id": row["id"], "nome": row["nome"], "filtro": filtro, "created_at": row["created_at"]})
        return out

    def excluir_filtro_quiz(self, filtro_id: int, user_id: int) -> None:
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM quiz_filtros_salvos WHERE id = ? AND user_id = ?", (filtro_id, user_id))
        conn.commit()
        conn.close()

    def topicos_revisao(self, user_id: int, limite: int = 3) -> List[Dict]:
        conn = self.conectar()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT tema, SUM(erros) AS erros_total, SUM(acertos) AS acertos_total, SUM(tentativas) AS tentativas_total
            FROM questoes_usuario
            WHERE user_id = ?
            GROUP BY tema
            HAVING tentativas_total > 0
            ORDER BY (erros_total - acertos_total) DESC, erros_total DESC, tentativas_total DESC
            LIMIT ?
            """,
            (user_id, int(max(1, limite))),
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def revisoes_pendentes(self, user_id: int) -> int:
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM questoes_usuario
            WHERE user_id = ?
              AND proxima_revisao IS NOT NULL
              AND DATETIME(proxima_revisao) <= DATETIME('now')
            """,
            (user_id,),
        )
        total = cursor.fetchone()[0]
        conn.close()
        return int(total or 0)

    def sugerir_estudo_agora(self, user_id: int) -> Dict:
        topicos = self.topicos_revisao(user_id, limite=1)
        if topicos:
            tema = topicos[0].get("tema") or "Geral"
            return {
                "topic": tema,
                "difficulty": "intermediario",
                "count": 5,
                "session_mode": "erradas",
                "reason": f"Maior necessidade atual: {tema}",
            }
        return {
            "topic": "Geral",
            "difficulty": "intermediario",
            "count": 5,
            "session_mode": "nova",
            "reason": "Comece uma sessao nova para gerar historico.",
        }

    def salvar_plano_semanal(
        self,
        user_id: int,
        objetivo: str,
        data_prova: str,
        tempo_diario_min: int,
        itens: List[Dict],
    ) -> int:
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE study_plan_runs SET status = 'arquivado'
            WHERE user_id = ? AND status = 'ativo'
            """,
            (user_id,),
        )
        cursor.execute(
            """
            INSERT INTO study_plan_runs (user_id, objetivo, data_prova, tempo_diario_min, status)
            VALUES (?, ?, ?, ?, 'ativo')
            """,
            (user_id, objetivo, data_prova, int(max(30, tempo_diario_min))),
        )
        plan_id = int(cursor.lastrowid or 0)
        for item in itens:
            cursor.execute(
                """
                INSERT INTO study_plan_items (plan_id, dia, tema, atividade, duracao_min, prioridade, concluido)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_id,
                    str(item.get("dia") or "Dia"),
                    str(item.get("tema") or "Geral"),
                    str(item.get("atividade") or "Resolver questoes"),
                    int(item.get("duracao_min") or 60),
                    int(item.get("prioridade") or 1),
                    1 if item.get("concluido") else 0,
                ),
            )
        conn.commit()
        conn.close()
        return plan_id

    def obter_plano_ativo(self, user_id: int) -> Dict:
        conn = self.conectar()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM study_plan_runs
            WHERE user_id = ? AND status = 'ativo'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        plan = cursor.fetchone()
        if not plan:
            conn.close()
            return {"plan": None, "itens": []}
        cursor.execute(
            """
            SELECT *
            FROM study_plan_items
            WHERE plan_id = ?
            ORDER BY id ASC
            """,
            (plan["id"],),
        )
        itens = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return {"plan": dict(plan), "itens": itens}

    def marcar_item_plano(self, item_id: int, concluido: bool) -> None:
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE study_plan_items SET concluido = ? WHERE id = ?",
            (1 if concluido else 0, item_id),
        )
        conn.commit()
        conn.close()

    def salvar_study_package(self, user_id: int, titulo: str, source_nome: str, dados: Dict) -> int:
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO study_packages (user_id, titulo, source_nome, dados_json)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, titulo, source_nome, json.dumps(dados, ensure_ascii=False)),
        )
        package_id = int(cursor.lastrowid or 0)
        conn.commit()
        conn.close()
        return package_id

    def listar_study_packages(self, user_id: int, limite: int = 20) -> List[Dict]:
        conn = self.conectar()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, titulo, source_nome, dados_json, created_at
            FROM study_packages
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, int(max(1, limite))),
        )
        rows = cursor.fetchall()
        conn.close()
        out = []
        for row in rows:
            try:
                dados = json.loads(row["dados_json"] or "{}")
            except Exception:
                dados = {}
            out.append(
                {
                    "id": row["id"],
                    "titulo": row["titulo"],
                    "source_nome": row["source_nome"],
                    "dados": dados,
                    "created_at": row["created_at"],
                }
            )
        return out

    def salvar_nota_questao(self, user_id: int, question: Dict, nota: str) -> None:
        qhash = self._question_hash(question)
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO questoes_notas (user_id, qhash, nota, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, qhash) DO UPDATE SET
                nota = excluded.nota,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, qhash, nota or ""),
        )
        conn.commit()
        conn.close()

    def obter_nota_questao(self, user_id: int, question: Dict) -> str:
        qhash = self._question_hash(question)
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT nota FROM questoes_notas WHERE user_id = ? AND qhash = ?",
            (user_id, qhash),
        )
        row = cursor.fetchone()
        conn.close()
        return str(row[0]) if row and row[0] is not None else ""


# Nao criar instancia global em import para evitar inicializacao prematura
# (especialmente no Android empacotado).





