from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func

from backend.database.connection import Base


class Visitor(Base):
    """
    Registro individual de cada visitante da aplicação.

    Armazena informações detalhadas de cada visitante para:
    - Rastreamento preciso de visitantes únicos
    - Análise de comportamento
    - Estatísticas em tempo real
    - Auditoria de acesso

    Attributes:
        id: Chave primária auto-incrementada
        visitor_id: ID único do visitante (UUID gerado pelo frontend)
        session_id: ID da sessão atual (referência para user_session_cache)
        user_id: ID do usuário se estiver logado (referência para admin_users)
        ip_address: Endereço IP do visitante
        user_agent: User-Agent do navegador
        referrer: Página de origem
        first_visit: Data/hora da primeira visita
        last_visit: Data/hora da última visita
        visit_count: Número total de visitas
        is_active: Se a sessão está ativa
        country: País detectado (opcional)
        city: Cidade detectada (opcional)
        device_type: Tipo de dispositivo (desktop, mobile, tablet)
        browser: Navegador usado
        os: Sistema operacional

    Indexes:
        idx_visitor_visitor_id: Para busca por visitor_id
        idx_visitor_session_id: Para busca por sessão
        idx_visitor_last_visit: Para limpeza de sessões antigas
        idx_visitor_ip: Para análise de tráfego
    """

    __tablename__ = "visitors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    visitor_id = Column(
        String(36),
        nullable=False,
        unique=True,
        index=True,
        comment="UUID único do visitante (formato: visitor_xxx)",
    )
    session_id = Column(
        String(50),
        nullable=True,
        index=True,
        comment="ID da sessão atual (user_session_cache.session_id)",
    )
    user_id = Column(
        Integer,
        nullable=True,
        index=True,
        comment="ID do usuário logado (admin_users.id)",
    )
    ip_address = Column(
        String(45),
        nullable=True,
        index=True,
        comment="Endereço IP (IPv4 ou IPv6)",
    )
    user_agent = Column(
        Text, nullable=True, comment="User-Agent completo do navegador"
    )
    referrer = Column(
        Text, nullable=True, comment="URL de referência (de onde veio)"
    )
    first_visit = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="Data/hora da primeira visita",
    )
    last_visit = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Data/hora da última visita",
    )
    visit_count = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Número total de visitas/visitas de página",
    )
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Se a sessão está ativa (não expirou)",
    )
    country = Column(
        String(100), nullable=True, comment="País detectado por geolocalização"
    )
    city = Column(
        String(100),
        nullable=True,
        comment="Cidade detectada por geolocalização",
    )
    last_latitude = Column(
        Float, nullable=True, comment="Última latitude registrada"
    )
    last_longitude = Column(
        Float, nullable=True, comment="Última longitude registrada"
    )
    geolocation_accuracy = Column(
        Float, nullable=True, comment="Precisão da geolocalização (metros)"
    )
    device_type = Column(
        String(20), nullable=True, comment="Tipo: desktop, mobile, tablet"
    )
    browser = Column(
        String(50),
        nullable=True,
        comment="Navegador: chrome, firefox, safari, etc",
    )
    os = Column(
        String(50),
        nullable=True,
        comment="SO: windows, macos, linux, android, ios",
    )

    def __repr__(self) -> str:
        try:
            vid = getattr(self, "visitor_id", "uninitialized")
            visits = getattr(self, "visit_count", 0)
            active = getattr(self, "is_active", False)
            return (
                f"<Visitor(id='{vid[:12]}...', visits={visits}, "
                f"active={active})>"
            )
        except Exception:
            return "<Visitor(uninitialized)>"

    def to_dict(self) -> dict:
        """
        Converte para dicionário.

        Returns:
            dict: Dados completos do visitante
        """
        return {
            "id": self.id,
            "visitor_id": self.visitor_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "referrer": self.referrer,
            "first_visit": getattr(self, "first_visit", None),
            "last_visit": getattr(self, "last_visit", None),
            "visit_count": self.visit_count,
            "is_active": self.is_active,
            "country": self.country,
            "city": self.city,
            "device_type": self.device_type,
            "browser": self.browser,
            "os": self.os,
        }

    def update_visit(self):
        """
        Atualiza informações quando o visitante faz uma nova visita.
        """
        self.last_visit = datetime.utcnow()
        self.visit_count += 1
        self.is_active = True

    @classmethod
    def create_or_update(
        cls,
        visitor_id: str,
        session_id: Optional[str] = None,
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        **kwargs,
    ):
        """
        Cria um novo visitante ou atualiza um existente.

        Args:
            visitor_id: UUID único do visitante
            session_id: ID da sessão atual
            user_id: ID do usuário logado (opcional)
            ip_address: Endereço IP
            user_agent: User-Agent do navegador
            **kwargs: Outros campos opcionais

        Returns:
            tuple: (visitor_instance, is_new_visitor)
        """
        # Lógica seria implementada na camada de serviço
        # Aqui apenas definimos a interface
        pass


class VisitorStats(Base):
    """
    Estatísticas agregadas calculadas a partir dos visitantes individuais.

    Esta tabela contém estatísticas pré-calculadas para performance.
    Os dados são atualizados periodicamente a partir da tabela visitors.

    Attributes:
        id: Chave primária (sempre 1, uma única linha)
        total_visitors: Total de visitantes únicos (calculado)
        unique_visitors_today: Visitantes únicos hoje
        unique_visitors_week: Visitantes únicos na semana
        unique_visitors_month: Visitantes únicos no mês
        active_sessions: Sessões ativas agora
        last_sync: Última sincronização com tabela visitors
        peak_hour: Hora de pico do dia
        top_country: País com mais visitantes
        top_city: Cidade com mais visitantes
        created_at: Data/hora de criação
        updated_at: Data/hora da última atualização
    """

    __tablename__ = "visitor_stats"

    id = Column(
        Integer,
        primary_key=True,
        default=1,
        comment="Sempre 1 - tabela com uma única linha",
    )
    total_visitors = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Total de visitantes únicos históricos",
    )
    unique_visitors_today = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Visitantes únicos hoje",
    )
    unique_visitors_week = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Visitantes únicos na semana",
    )
    unique_visitors_month = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Visitantes únicos no mês",
    )
    active_sessions = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Sessões ativas (últimos 30 min)",
    )
    last_sync = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="Última sincronização com visitors",
    )
    peak_hour = Column(
        String(5), nullable=True, comment="Hora de pico (HH:MM)"
    )
    top_country = Column(
        String(100), nullable=True, comment="País com mais visitantes"
    )
    top_city = Column(
        String(100), nullable=True, comment="Cidade com mais visitantes"
    )
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="Data/hora de criação",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Data/hora da última atualização",
    )

    def __repr__(self) -> str:
        try:
            total = getattr(self, "total_visitors", 0)
            today = getattr(self, "unique_visitors_today", 0)
            active = getattr(self, "active_sessions", 0)
            return (
                f"<VisitorStats(total={total}, today={today}, "
                f"active={active})>"
            )
        except Exception:
            return "<VisitorStats(uninitialized)>"

    def to_dict(self) -> dict:
        """
        Converte para dicionário com todas as estatísticas.

        Returns:
            dict: Estatísticas completas
        """
        return {
            "id": self.id,
            "total_visitors": self.total_visitors,
            "unique_visitors_today": self.unique_visitors_today,
            "unique_visitors_week": self.unique_visitors_week,
            "unique_visitors_month": self.unique_visitors_month,
            "active_sessions": self.active_sessions,
            "last_sync": getattr(self, "last_sync", None),
            "peak_hour": self.peak_hour,
            "top_country": self.top_country,
            "top_city": self.top_city,
            "created_at": getattr(self, "created_at", None),
            "updated_at": getattr(self, "updated_at", None),
        }


# Índices para performance
Index(
    "idx_visitor_visitor_id",
    Visitor.visitor_id,
    unique=True,
    postgresql_using="btree",
)

Index("idx_visitor_session_id", Visitor.session_id, postgresql_using="btree")

Index("idx_visitor_last_visit", Visitor.last_visit, postgresql_using="btree")

Index("idx_visitor_ip", Visitor.ip_address, postgresql_using="btree")

Index(
    "idx_visitor_active",
    Visitor.is_active,
    Visitor.last_visit,
    postgresql_using="btree",
)


__all__ = ["Visitor", "VisitorStats"]
