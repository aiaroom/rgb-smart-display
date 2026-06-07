from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Table,
    JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


# Связь пользователей УК с дисплеями
# Например, сотрудник может управлять только частью экранов
user_displays = Table(
    "user_displays",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("display_id", Integer, ForeignKey("displays.id"), primary_key=True),
)


# Связь дисплеев с группами
# Один дисплей может входить в несколько групп
display_group_items = Table(
    "display_group_items",
    Base.metadata,
    Column("display_id", Integer, ForeignKey("displays.id"), primary_key=True),
    Column("group_id", Integer, ForeignKey("display_groups.id"), primary_key=True),
)

class Building(Base):
    """
    Дом / корпус внутри ЖК.
    В одном ЖК может быть несколько домов.
    """

    __tablename__ = "buildings"

    id = Column(Integer, primary_key=True, index=True)

    complex_id = Column(Integer, ForeignKey("residential_complexes.id"), nullable=False)

    name = Column(String, nullable=False)
    address = Column(Text, nullable=True)

    # Например: корпус 1, башня A, дом 2
    building_number = Column(String, nullable=True)

    # ID дома из Ujin, если есть
    ujin_building_id = Column(String, nullable=True, index=True)

    is_active = Column(Boolean, default=True)

    meta = Column(JSON, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    complex = relationship("ResidentialComplex", back_populates="buildings")
    displays = relationship("Display", back_populates="building")
    display_groups = relationship("DisplayGroup", back_populates="building")

class ResidentialComplex(Base):
    """
    Главная таблица ЖК.
    От неё идут экраны, группы экранов, шаблоны, контент, ЧС и интеграция с Ujin.
    """

    __tablename__ = "residential_complexes"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    address = Column(Text, nullable=True)

    # ID ЖК из Ujin, если получаем ЖК через API Ujin
    ujin_complex_id = Column(String, nullable=True, index=True)

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    displays = relationship("Display", back_populates="complex")
    display_groups = relationship("DisplayGroup", back_populates="complex")
    # templates = relationship("Template", back_populates="complex")
    content_items = relationship("ContentItem", back_populates="complex")
    emergency_states = relationship("EmergencyState", back_populates="complex")
    emergency_logs = relationship("EmergencyLog", back_populates="complex")
    ujin_tokens = relationship("UjinToken", back_populates="complex")
    buildings = relationship("Building", back_populates="complex")


class User(Base):
    """
    Сотрудник УК.
    Авторизацию оставляем как есть, но добавляем привязку к ЖК.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    email = Column(Text, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    company_name = Column(String, nullable=True)

    hashed_password = Column(String, nullable=False)

    # role:
    # uk_admin - администратор УК
    # dispatcher - диспетчер
    # concierge - консьерж
    role = Column(String, default="dispatcher", nullable=False)

    complex_id = Column(Integer, ForeignKey("residential_complexes.id"), nullable=True)

    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    complex = relationship("ResidentialComplex")
    displays = relationship("Display", secondary=user_displays, back_populates="users")

    emergency_logs = relationship("EmergencyLog", back_populates="created_by")


class Display(Base):
    """
    Физический экран в ЖК: холл, лифт, ресепшн и т.д.
    """

    __tablename__ = "displays"

    id = Column(Integer, primary_key=True, index=True)

    complex_id = Column(Integer, ForeignKey("residential_complexes.id"), nullable=False)

    name = Column(String, nullable=False)
    code = Column(String, unique=True, index=True, nullable=False)

    # hall / elevator / reception / entrance / other
    location_type = Column(String, default="hall", nullable=False)

    location_title = Column(String, nullable=True)

    entrance = Column(String, nullable=True)
    floor = Column(String, nullable=True)

    # portrait / landscape
    orientation = Column(String, default="portrait", nullable=False)

    resolution_width = Column(Integer, default=1080)
    resolution_height = Column(Integer, default=1920)

    current_template_id = Column(Integer, ForeignKey("templates.id"), nullable=True)

    is_online = Column(Boolean, default=False)
    last_ping = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)

    last_seen_at = Column(DateTime(timezone=True), nullable=True)

    meta = Column(JSON, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    complex = relationship("ResidentialComplex", back_populates="displays")
    building_id = Column(Integer, ForeignKey("buildings.id"), nullable=True)
    building = relationship("Building", back_populates="displays")

    current_template = relationship(
        "Template",
        foreign_keys=[current_template_id],
        post_update=True,
    )

    users = relationship("User", secondary=user_displays, back_populates="displays")
    groups = relationship(
        "DisplayGroup",
        secondary=display_group_items,
        back_populates="displays",
    )

    emergency_states = relationship("EmergencyState", back_populates="display")


class DisplayGroup(Base):
    """
    Группа экранов.
    Например: все экраны подъезда 3, все лифты, все ресепшн.
    """

    __tablename__ = "display_groups"

    id = Column(Integer, primary_key=True, index=True)

    complex_id = Column(Integer, ForeignKey("residential_complexes.id"), nullable=False)

    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    complex = relationship("ResidentialComplex", back_populates="display_groups")
    displays = relationship(
        "Display",
        secondary=display_group_items,
        back_populates="groups",
    )

    emergency_states = relationship("EmergencyState", back_populates="group")
    building_id = Column(Integer, ForeignKey("buildings.id"), nullable=True)
    building = relationship("Building", back_populates="display_groups")


class Template(Base):
    """
    Шаблон отображения.
    Здесь храним сетку, тему, виджеты и настройки внешнего вида.
    """

    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, index=True)


    name = Column(String, nullable=False)

    # light / dark / custom
    theme = Column(String, default="light", nullable=False)

    # Настройки сетки: 3/4/6 колонок, отступы, размеры
    grid_config = Column(JSON, default=dict)

    # Общие настройки дизайна: фон, цвета, шрифты
    style_config = Column(JSON, default=dict)

    # Виджеты шаблона
    widgets = Column(JSON, default=list)

    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)

    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # complex = relationship("ResidentialComplex", back_populates="templates")
    created_by = relationship("User")


class ContentItem(Base):
    """
    Локальный контент УК.
    Например: правила ЖК, график вывоза мусора, контакты аварийной службы.
    """

    __tablename__ = "content_items"

    id = Column(Integer, primary_key=True, index=True)

    complex_id = Column(Integer, ForeignKey("residential_complexes.id"), nullable=False)

    title = Column(String, nullable=False)
    body = Column(Text, nullable=True)

    # static_info / rule / trash_schedule / emergency_contact / partner_bonus / custom
    content_type = Column(String, default="static_info", nullable=False)

    image_url = Column(Text, nullable=True)
    file_url = Column(Text, nullable=True)

    # Дополнительные настройки отображения
    config = Column(JSON, default=dict)

    is_active = Column(Boolean, default=True)

    publish_from = Column(DateTime(timezone=True), nullable=True)
    publish_to = Column(DateTime(timezone=True), nullable=True)

    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    complex = relationship("ResidentialComplex", back_populates="content_items")
    created_by = relationship("User")


class UjinToken(Base):
    """
    Токен и настройки интеграции с Ujin.
    Лучше хранить отдельно по каждому ЖК.
    """

    __tablename__ = "ujin_tokens"

    id = Column(Integer, primary_key=True, index=True)

    complex_id = Column(Integer, ForeignKey("residential_complexes.id"), nullable=True)

    name = Column(String, nullable=False, default="default")

    base_url = Column(Text, nullable=False)
    token = Column(Text, nullable=False)

    is_active = Column(Boolean, default=True)

    last_sync_at = Column(DateTime(timezone=True), nullable=True)

    meta = Column(JSON, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    complex = relationship("ResidentialComplex", back_populates="ujin_tokens")


class EmergencyState(Base):
    """
    Текущее активное ЧС.
    ЧС не является частью шаблона и отображается поверх любого контента.
    """

    __tablename__ = "emergency_states"

    id = Column(Integer, primary_key=True, index=True)

    complex_id = Column(Integer, ForeignKey("residential_complexes.id"), nullable=False)

    # display / group / complex
    target_type = Column(String, nullable=False)

    display_id = Column(Integer, ForeignKey("displays.id"), nullable=True)
    group_id = Column(Integer, ForeignKey("display_groups.id"), nullable=True)

    emergency_text = Column(Text, nullable=False)

    priority = Column(Integer, default=1)

    is_active = Column(Boolean, default=True)

    activated_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    activated_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    reset_at = Column(DateTime(timezone=True), nullable=True)

    meta = Column(JSON, default=dict)

    complex = relationship("ResidentialComplex", back_populates="emergency_states")
    display = relationship("Display", back_populates="emergency_states")
    group = relationship("DisplayGroup", back_populates="emergency_states")
    activated_by = relationship("User")


class EmergencyLog(Base):
    """
    Аудит действий по режиму ЧС.
    По заданию нужно логировать кто, когда, куда и какой текст отправил.
    """

    __tablename__ = "emergency_logs"

    id = Column(Integer, primary_key=True, index=True)

    complex_id = Column(Integer, ForeignKey("residential_complexes.id"), nullable=False)

    # activate / reset / replace / expired
    action = Column(String, nullable=False)

    # display / group / complex
    target_type = Column(String, nullable=False)

    target_id = Column(Integer, nullable=True)

    emergency_text = Column(Text, nullable=True)

    priority = Column(Integer, nullable=True)

    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    meta = Column(JSON, default=dict)

    complex = relationship("ResidentialComplex", back_populates="emergency_logs")
    created_by = relationship("User", back_populates="emergency_logs")