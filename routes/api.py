from datetime import datetime, timezone, timedelta
from typing import Any
from sqlalchemy import or_, select, insert, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import (
    Building,
    ContentItem,
    Display,
    EmergencyState,
    ResidentialComplex,
    Template,
    User,
    DisplayGroup,
    display_group_items,
    EmergencyLog

)
from routes.auth import get_current_user_info
from routes.shemas import (
    DisplayPayload,
    ResidentialComplexCreate,
    ResidentialComplexResponse,
    UjinSyncRequest,
    UjinSyncResponse,
    DisplayCreate,
    DisplayUpdate,
    DisplayResponse,
    BuildingCreate,
    BuildingResponse,
    TemplateCreate,
    TemplateUpdate,
    TemplateResponse,
    TemplateSendRequest,
    DisplayGroupCreate,
    DisplayGroupResponse,
    EmergencyActivate,
    EmergencyStateResponse,
    EmergencyReset,
    ContentItemCreate,
    ContentItemResponse,
    ContentItemUpdate,
)
from ujin_client import UjinClient
from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter()

def _require_same_complex(user: User, complex_id: int) -> None:
    if user.is_admin:
        return

    if user.complex_id != complex_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied for this complex",
        )

def _building_address(building_info: dict[str, Any]) -> str | None:
    address = building_info.get("address")

    if isinstance(address, str):
        return address

    if isinstance(address, dict):
        return (
            address.get("title")
            or address.get("full")
            or address.get("address")
        )

    return None


def _count_parking_spots(data: dict[str, Any]) -> dict[str, Any]:
    total = 0
    free = 0
    occupied = 0
    public = 0
    private = 0
    unassigned = 0

    for complex_item in data.get("data", {}).get("items", []):
        for building in complex_item.get("buildings", []):
            for zone in building.get("zones", []):
                for spot in zone.get("spots", []):
                    total += 1

                    status_value = spot.get("status")
                    assignment = spot.get("assignment_type")

                    if status_value == "free":
                        free += 1

                    if status_value == "occupied":
                        occupied += 1

                    if assignment == "public":
                        public += 1

                    if assignment == "private":
                        private += 1

                    if assignment == "unassigned":
                        unassigned += 1

    return {
        "total": total,
        "free": free,
        "occupied": occupied,
        "public": public,
        "private": private,
        "unassigned": unassigned,
    }


def _count_storage_rooms(data: dict[str, Any]) -> dict[str, Any]:
    total = 0
    free = 0
    occupied = 0
    public = 0
    private = 0
    unassigned = 0

    for complex_item in data.get("data", {}).get("items", []):
        for building in complex_item.get("buildings", []):
            for room in building.get("rooms", []):
                total += 1

                status_value = room.get("status")
                assignment = room.get("assignment_type")

                if status_value == "free":
                    free += 1

                if status_value == "occupied":
                    occupied += 1

                if assignment == "public":
                    public += 1

                if assignment == "private":
                    private += 1

                if assignment == "unassigned":
                    unassigned += 1

    return {
        "total": total,
        "free": free,
        "occupied": occupied,
        "public": public,
        "private": private,
        "unassigned": unassigned,
    }


async def _upsert_system_content(
    db: AsyncSession,
    complex_id: int,
    content_type: str,
    title: str,
    body: str | None,
    config: dict[str, Any],
    publish_from: datetime | None = None,
    publish_to: datetime | None = None,
) -> tuple[ContentItem, bool]:
    ujin_id = config.get("ujin_id")

    stmt = select(ContentItem).where(
        ContentItem.complex_id == complex_id,
        ContentItem.content_type == content_type,
    )

    if ujin_id is not None:
        stmt = stmt.where(
            ContentItem.config["ujin_id"].as_string() == str(ujin_id)
        )
    else:
        stmt = stmt.where(ContentItem.title == title)

    item = (await db.execute(stmt)).scalar_one_or_none()
    created = item is None

    if item is None:
        item = ContentItem(
            complex_id=complex_id,
            content_type=content_type,
        )
        db.add(item)

    item.title = title
    item.body = body
    item.config = config
    item.is_active = True
    item.publish_from = publish_from
    item.publish_to = publish_to

    return item, created


async def _build_ujin_payload_from_db(
    db: AsyncSession,
    display: Display,
) -> dict[str, Any]:
    result = await db.execute(
        select(ContentItem).where(
            ContentItem.complex_id == display.complex_id,
            ContentItem.is_active.is_(True),
            ContentItem.content_type.in_(
                [
                    "ujin_news",
                    "parking_stats",
                    "storage_stats",
                ]
            ),
        )
    )

    items = result.scalars().all()

    news = []
    parking: dict[str, Any] = {}
    storage: dict[str, Any] = {}

    for item in items:
        if item.content_type == "ujin_news":
            news.append(
                {
                    "id": item.config.get("ujin_id"),
                    "title": item.title,
                    "text": item.body,
                    "date": item.config.get("date"),
                    "type": item.config.get("type"),
                    "buildings": item.config.get("buildings", []),
                    "images": item.config.get("images", []),
                }
            )

        elif item.content_type == "parking_stats":
            parking = item.config

        elif item.content_type == "storage_stats":
            storage = item.config

    return {
        "news": news,
        "parking": parking,
        "storage": storage,
    }

@router.post("/complexes", response_model=ResidentialComplexResponse)
async def create_complex(
    payload: ResidentialComplexCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    data = payload.model_dump()

    if payload.ujin_complex_id:
        ujin_complex = await UjinClient().find_complex_by_id(
            payload.ujin_complex_id
        )

        if ujin_complex is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Complex not found in Ujin",
            )

        data["name"] = ujin_complex.get("title") or data["name"]

        region = ujin_complex.get("region") or {}
        data["address"] = data.get("address") or region.get("title")
        data["ujin_complex_id"] = str(payload.ujin_complex_id)

        existing = await db.execute(
            select(ResidentialComplex).where(
                ResidentialComplex.ujin_complex_id == data["ujin_complex_id"]
            )
        )

        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Complex with this ujin_complex_id already exists",
            )

    complex_obj = ResidentialComplex(**data)

    db.add(complex_obj)
    await db.commit()
    await db.refresh(complex_obj)

    if complex_obj.ujin_complex_id:
        try:
            await sync_complex_from_ujin(
                complex_id=complex_obj.id,
                payload=UjinSyncRequest(
                    complex_id=complex_obj.id,
                    sync_complex=True,
                    sync_buildings=True,
                    sync_news=True,
                    sync_parking=True,
                    sync_storage=True,
                ),
                db=db,
                user=user,
            )
        except Exception as exc:
            print(f"Ujin sync failed for complex {complex_obj.id}: {exc}")

    return complex_obj

@router.get("/complexes", response_model=list[ResidentialComplexResponse])
async def get_complexes(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    stmt = select(ResidentialComplex).where(
        ResidentialComplex.is_active.is_(True)
    )

    if not user.is_admin:
        stmt = stmt.where(ResidentialComplex.id == user.complex_id)

    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/buildings", response_model=BuildingResponse)
async def create_building(
    payload: BuildingCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    _require_same_complex(user, payload.complex_id)

    building = Building(**payload.model_dump())

    db.add(building)
    await db.commit()
    await db.refresh(building)

    return building


@router.get("/buildings", response_model=list[BuildingResponse])
async def get_buildings(
    complex_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    _require_same_complex(user, complex_id)

    result = await db.execute(
        select(Building).where(
            Building.complex_id == complex_id,
            Building.is_active.is_(True),
        )
    )

    return result.scalars().all()

@router.get("/buildings/{building_id}", response_model=BuildingResponse)
async def get_building(
    building_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    result = await db.execute(
        select(Building).where(
            Building.id == building_id,
            Building.is_active.is_(True),
        )
    )

    building = result.scalar_one_or_none()

    if building is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Building not found",
        )

    _require_same_complex(user, building.complex_id)

    return building


@router.patch("/buildings/{building_id}", response_model=BuildingResponse)
async def update_building(
    building_id: int,
    payload: BuildingCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    result = await db.execute(
        select(Building).where(Building.id == building_id)
    )

    building = result.scalar_one_or_none()

    if building is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Building not found",
        )

    _require_same_complex(user, building.complex_id)
    _require_same_complex(user, payload.complex_id)

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(building, key, value)

    await db.commit()
    await db.refresh(building)

    return building


@router.delete("/buildings/{building_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_building(
    building_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    result = await db.execute(
        select(Building).where(Building.id == building_id)
    )

    building = result.scalar_one_or_none()

    if building is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Building not found",
        )

    _require_same_complex(user, building.complex_id)

    building.is_active = False

    await db.commit()

    return None

@router.post(
    "/complexes/{complex_id}/sync-ujin",
    response_model=UjinSyncResponse,
)
async def sync_complex_from_ujin(
    complex_id: int,
    payload: UjinSyncRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    _require_same_complex(user, complex_id)

    result = await db.execute(
        select(ResidentialComplex).where(
            ResidentialComplex.id == complex_id
        )
    )

    complex_obj = result.scalar_one_or_none()

    if complex_obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complex not found",
        )

    if not complex_obj.ujin_complex_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="complex.ujin_complex_id is required for Ujin sync",
        )

    options = payload or UjinSyncRequest(complex_id=complex_id)
    ujin = UjinClient()

    response = UjinSyncResponse(
        complex_id=complex_id,
        ujin_complex_id=complex_obj.ujin_complex_id,
    )

    if options.sync_complex:
        ujin_complex = await ujin.find_complex_by_id(
            complex_obj.ujin_complex_id
        )

        if ujin_complex:
            complex_obj.name = ujin_complex.get("title") or complex_obj.name

            region = ujin_complex.get("region") or {}
            complex_obj.address = (
                complex_obj.address
                or region.get("title")
            )

            response.synced_complex = True

    if options.sync_buildings:
        buildings = await ujin.get_buildings(
            complex_id=complex_obj.ujin_complex_id
        )

        for raw in buildings:
            building_info = raw.get("building") or raw
            ujin_building_id = building_info.get("id")

            if not ujin_building_id:
                continue

            ujin_building_id = str(ujin_building_id)

            result = await db.execute(
                select(Building).where(
                    Building.ujin_building_id == ujin_building_id
                )
            )

            building = result.scalar_one_or_none()
            created = building is None

            if building is None:
                building = Building(
                    complex_id=complex_id,
                    ujin_building_id=ujin_building_id,
                )
                db.add(building)

            building.complex_id = complex_id
            building.name = (
                building_info.get("title")
                or f"Корпус {ujin_building_id}"
            )
            building.address = _building_address(building_info)
            building.building_number = (
                building_info.get("alias")
                or building_info.get("title")
            )
            building.meta = raw
            building.is_active = True

            if created:
                response.buildings_created += 1
            else:
                response.buildings_updated += 1

    if options.sync_news:
        news_items = await ujin.get_news(
            complexes=[int(complex_obj.ujin_complex_id)]
        )

        for news in news_items:
            detail = None

            if news.get("id"):
                detail = await ujin.get_news_detail(int(news["id"]))

            full_news = detail or news

            config = {
                "source": "ujin",
                "ujin_id": str(full_news.get("id")),
                "date": full_news.get("date") or news.get("date"),
                "type": full_news.get("type") or news.get("type"),
                "buildings": (
                    full_news.get("buildings")
                    or news.get("buildings", [])
                ),
                "images": full_news.get("images", []),
                "raw": full_news,
            }

            _, created = await _upsert_system_content(
                db=db,
                complex_id=complex_id,
                content_type="ujin_news",
                title=(
                    full_news.get("title")
                    or news.get("title")
                    or "Новость УК"
                ),
                body=full_news.get("text") or news.get("text"),
                config=config,
            )

            if created:
                response.news_created += 1
            else:
                response.news_updated += 1

    if options.sync_parking:
        parking_raw = await ujin.get_parking(
            complexes=[int(complex_obj.ujin_complex_id)],
            status_filter="unassigned",
        )

        parking_stats = _count_parking_spots(parking_raw)
        response.parking_items = parking_stats["total"]

        await _upsert_system_content(
            db=db,
            complex_id=complex_id,
            content_type="parking_stats",
            title="Свободные парковочные места",
            body=(
                "Невыкупленных парковочных мест: "
                f"{parking_stats['unassigned']}"
            ),
            config={
                "source": "ujin",
                "kind": "parking",
                "status_filter": "unassigned",
                "stats": parking_stats,
                "raw": parking_raw,
            },
        )

    if options.sync_storage:
        storage_raw = await ujin.get_storage(
            complexes=[int(complex_obj.ujin_complex_id)],
            status_filter="unassigned",
        )

        storage_stats = _count_storage_rooms(storage_raw)
        response.storage_items = storage_stats["total"]

        await _upsert_system_content(
            db=db,
            complex_id=complex_id,
            content_type="storage_stats",
            title="Свободные кладовые",
            body=(
                "Невыкупленных кладовых: "
                f"{storage_stats['unassigned']}"
            ),
            config={
                "source": "ujin",
                "kind": "storage",
                "status_filter": "unassigned",
                "stats": storage_stats,
                "raw": storage_raw,
            },
        )

    await db.commit()

    return response

@router.get("/display/{code}/payload", response_model=DisplayPayload)
async def display_payload(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Display).where(
            Display.code == code,
            Display.is_active.is_(True),
        )
    )

    display = result.scalar_one_or_none()

    if display is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Display not found",
        )

    display.is_online = True
    display.last_seen_at = datetime.now(timezone.utc)

    template = None

    if display.current_template_id:
        result = await db.execute(
            select(Template).where(
                Template.id == display.current_template_id,
                Template.is_active.is_(True),
            )
        )
        template = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    content_items = (
        await db.execute(
            select(ContentItem).where(
                ContentItem.complex_id == display.complex_id,
                ContentItem.is_active.is_(True),
                ~ContentItem.content_type.in_(
                    [
                        "ujin_news",
                        "parking_stats",
                        "storage_stats",
                    ]
                ),
                or_(
                    ContentItem.publish_from.is_(None),
                    ContentItem.publish_from <= now,
                ),
                or_(
                    ContentItem.publish_to.is_(None),
                    ContentItem.publish_to >= now,
                ),
            )
        )
    ).scalars().all()

    group_ids_result = await db.execute(
        select(display_group_items.c.group_id).where(
            display_group_items.c.display_id == display.id
        )
    )

    group_ids = list(group_ids_result.scalars().all())

    emergency = (
        await db.execute(
            select(EmergencyState)
            .where(
                EmergencyState.complex_id == display.complex_id,
                EmergencyState.is_active.is_(True),
                or_(
                    EmergencyState.display_id == display.id,
                    EmergencyState.target_type == "complex",
                    EmergencyState.group_id.in_(group_ids) if group_ids else False,
                ),
                or_(
                    EmergencyState.expires_at.is_(None),
                    EmergencyState.expires_at >= now,
                ),
            )
            .order_by(EmergencyState.priority.desc())
        )
    ).scalar_one_or_none()

    ujin_data = await _build_ujin_payload_from_db(db, display)

    await db.commit()

    return {
        "display": display,
        "template": template,
        "content_items": content_items,
        "emergency": emergency,
        "ujin_data": ujin_data,
    }


@router.get("/complexes/import-options")
async def get_complex_import_options(
    user: User = Depends(get_current_user_info),
):
    complexes = await UjinClient().get_complexes()

    return [
        {
            "ujin_complex_id": str(item.get("id")),
            "name": item.get("title") or item.get("name"),
            "address": (item.get("region") or {}).get("title"),
        }
        for item in complexes
    ]

@router.post("/displays", response_model=DisplayResponse)
async def create_display(
    payload: DisplayCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    _require_same_complex(user, payload.complex_id)

    if payload.building_id is not None:
        result = await db.execute(
            select(Building).where(
                Building.id == payload.building_id,
                Building.complex_id == payload.complex_id,
                Building.is_active.is_(True),
            )
        )

        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Building not found in this complex",
            )

    existing = await db.execute(
        select(Display).where(Display.code == payload.code)
    )

    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Display with this code already exists",
        )

    display = Display(**payload.model_dump())

    db.add(display)
    await db.commit()
    await db.refresh(display)

    return display


@router.get("/displays", response_model=list[DisplayResponse])
async def get_displays(
    complex_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    stmt = select(Display).where(Display.is_active.is_(True))

    if complex_id is not None:
        _require_same_complex(user, complex_id)
        stmt = stmt.where(Display.complex_id == complex_id)
    elif not user.is_admin:
        stmt = stmt.where(Display.complex_id == user.complex_id)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/displays/{display_id}", response_model=DisplayResponse)
async def get_display(
    display_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    result = await db.execute(
        select(Display).where(Display.id == display_id)
    )

    display = result.scalar_one_or_none()

    if display is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Display not found",
        )

    _require_same_complex(user, display.complex_id)

    return display


@router.patch("/displays/{display_id}", response_model=DisplayResponse)
async def update_display(
    display_id: int,
    payload: DisplayUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    result = await db.execute(
        select(Display).where(Display.id == display_id)
    )

    display = result.scalar_one_or_none()

    if display is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Display not found",
        )

    _require_same_complex(user, display.complex_id)

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(display, key, value)

    await db.commit()
    await db.refresh(display)

    return display


@router.delete("/displays/{display_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_display(
    display_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    result = await db.execute(
        select(Display).where(Display.id == display_id)
    )

    display = result.scalar_one_or_none()

    if display is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Display not found",
        )

    _require_same_complex(user, display.complex_id)

    display.is_active = False

    await db.commit()

    return None

@router.post("/templates", response_model=TemplateResponse)
async def create_template(
    payload: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    _require_same_complex(user, payload.complex_id)

    template = Template(
        **payload.model_dump(),
        created_by_user_id=user.id,
    )

    db.add(template)
    await db.commit()
    await db.refresh(template)

    return template


@router.get("/templates", response_model=list[TemplateResponse])
async def get_templates(
    complex_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    _require_same_complex(user, complex_id)

    result = await db.execute(
        select(Template).where(
            Template.complex_id == complex_id,
            Template.is_active.is_(True),
        )
    )

    return result.scalars().all()


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    result = await db.execute(
        select(Template).where(Template.id == template_id)
    )

    template = result.scalar_one_or_none()

    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    _require_same_complex(user, template.complex_id)

    return template


@router.patch("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    payload: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    result = await db.execute(
        select(Template).where(Template.id == template_id)
    )

    template = result.scalar_one_or_none()

    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    _require_same_complex(user, template.complex_id)

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(template, key, value)

    await db.commit()
    await db.refresh(template)

    return template


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    result = await db.execute(
        select(Template).where(Template.id == template_id)
    )

    template = result.scalar_one_or_none()

    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    _require_same_complex(user, template.complex_id)

    template.is_active = False
    await db.commit()

    return None

@router.post("/templates/send")
async def send_template(
    payload: TemplateSendRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    result = await db.execute(
        select(Template).where(
            Template.id == payload.template_id,
            Template.is_active.is_(True),
        )
    )

    template = result.scalar_one_or_none()

    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    _require_same_complex(user, template.complex_id)

    if payload.target_type == "display":
        if payload.display_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="display_id is required",
            )

        result = await db.execute(
            select(Display).where(Display.id == payload.display_id)
        )

        display = result.scalar_one_or_none()

        if display is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Display not found",
            )

        _require_same_complex(user, display.complex_id)

        display.current_template_id = template.id

        await db.commit()

        return {
            "status": "ok",
            "target_type": "display",
            "display_id": display.id,
            "template_id": template.id,
        }

    if payload.target_type == "group":
        if payload.group_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="group_id is required",
            )

        result = await db.execute(
            select(DisplayGroup).where(
                DisplayGroup.id == payload.group_id,
                DisplayGroup.is_active.is_(True),
            )
        )

        group = result.scalar_one_or_none()

        if group is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Display group not found",
            )

        _require_same_complex(user, group.complex_id)

        result = await db.execute(
            select(Display)
            .join(display_group_items, display_group_items.c.display_id == Display.id)
            .where(
                display_group_items.c.group_id == group.id,
                Display.is_active.is_(True),
            )
        )

        displays = result.scalars().all()

        for display in displays:
            display.current_template_id = template.id

        await db.commit()

        return {
            "status": "ok",
            "target_type": "group",
            "group_id": group.id,
            "template_id": template.id,
            "displays_updated": len(displays),
        }

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Only display target is supported now",
    )

@router.post("/display-groups", response_model=DisplayGroupResponse)
async def create_display_group(
    payload: DisplayGroupCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    _require_same_complex(user, payload.complex_id)
    if payload.building_id is not None:
        result = await db.execute(
            select(Building).where(
                Building.id == payload.building_id,
                Building.complex_id == payload.complex_id,
                Building.is_active.is_(True),
            )
        )

        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Building not found in this complex",
            )

    group = DisplayGroup(
        complex_id=payload.complex_id,
        building_id=payload.building_id,
        name=payload.name,
        description=payload.description,
        is_active=True,
    )

    db.add(group)
    await db.flush()

    for display_id in payload.display_ids:
        result = await db.execute(
            select(Display).where(
                Display.id == display_id,
                Display.complex_id == payload.complex_id,
                Display.is_active.is_(True),
            )
        )

        display = result.scalar_one_or_none()

        if display is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Display {display_id} not found",
            )

        await db.execute(
            insert(display_group_items).values(
                group_id=group.id,
                display_id=display.id,
            )
        )

    await db.commit()
    await db.refresh(group)

    return group


@router.get("/display-groups", response_model=list[DisplayGroupResponse])
async def get_display_groups(
    complex_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    _require_same_complex(user, complex_id)

    result = await db.execute(
        select(DisplayGroup).where(
            DisplayGroup.complex_id == complex_id,
            DisplayGroup.is_active.is_(True),
        )
    )

    return result.scalars().all()


@router.patch("/display-groups/{group_id}", response_model=DisplayGroupResponse)
async def update_display_group(
    group_id: int,
    payload: DisplayGroupCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    result = await db.execute(
        select(DisplayGroup).where(DisplayGroup.id == group_id)
    )

    group = result.scalar_one_or_none()

    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Display group not found",
        )

    _require_same_complex(user, group.complex_id)
    if payload.building_id is not None:
        result = await db.execute(
            select(Building).where(
                Building.id == payload.building_id,
                Building.complex_id == payload.complex_id,
                Building.is_active.is_(True),
            )
        )

        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Building not found in this complex",
            )

    group.name = payload.name
    group.description = payload.description
    group.building_id = payload.building_id

    await db.execute(
        delete(display_group_items).where(
            display_group_items.c.group_id == group.id
        )
    )

    for display_id in payload.display_ids:
        result = await db.execute(
            select(Display).where(
                Display.id == display_id,
                Display.complex_id == group.complex_id,
                Display.is_active.is_(True),
            )
        )

        display = result.scalar_one_or_none()

        if display is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Display {display_id} not found",
            )

        await db.execute(
            insert(display_group_items).values(
                group_id=group.id,
                display_id=display.id,
            )
        )

    await db.commit()
    await db.refresh(group)

    return group


@router.delete("/display-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_display_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    result = await db.execute(
        select(DisplayGroup).where(DisplayGroup.id == group_id)
    )

    group = result.scalar_one_or_none()

    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Display group not found",
        )

    _require_same_complex(user, group.complex_id)

    group.is_active = False
    await db.commit()

    return None

@router.post("/emergency/activate", response_model=EmergencyStateResponse)
async def activate_emergency(
    payload: EmergencyActivate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    display_id = payload.display_id
    group_id = payload.group_id
    target_type = payload.target_type

    complex_id = payload.complex_id or user.complex_id

    if target_type == "display":
        if display_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="display_id is required",
            )

        result = await db.execute(
            select(Display).where(
                Display.id == display_id,
                Display.is_active.is_(True),
            )
        )
        display = result.scalar_one_or_none()

        if display is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Display not found",
            )

        _require_same_complex(user, display.complex_id)
        complex_id = display.complex_id

    elif target_type == "group":
        if group_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="group_id is required",
            )

        result = await db.execute(
            select(DisplayGroup).where(
                DisplayGroup.id == group_id,
                DisplayGroup.is_active.is_(True),
            )
        )
        group = result.scalar_one_or_none()

        if group is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Display group not found",
            )

        _require_same_complex(user, group.complex_id)
        complex_id = group.complex_id

    elif target_type == "complex":
        if complex_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="User is not linked to complex",
            )

        _require_same_complex(user, complex_id)

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid target_type",
        )

    now = datetime.now(timezone.utc)

    expires_at = None
    if payload.duration_minutes:
        expires_at = now + timedelta(minutes=payload.duration_minutes)

    await db.execute(
        update(EmergencyState)
        .where(
            EmergencyState.complex_id == complex_id,
            EmergencyState.is_active.is_(True),
        )
        .values(
            is_active=False,
            reset_at=now,
        )
    )

    emergency = EmergencyState(
        complex_id=complex_id,
        target_type=target_type,
        display_id=display_id if target_type == "display" else None,
        group_id=group_id if target_type == "group" else None,
        emergency_text=payload.emergency_text,
        priority=payload.priority,
        is_active=True,
        activated_by_user_id=user.id,
        activated_at=now,
        expires_at=expires_at,
        meta={
            "duration_minutes": payload.duration_minutes,
        },
    )

    db.add(emergency)
    await db.flush()

    log = EmergencyLog(
        complex_id=complex_id,
        action="activate",
        target_type=target_type,
        target_id=display_id or group_id or complex_id,
        emergency_text=payload.emergency_text,
        priority=payload.priority,
        created_by_user_id=user.id,
        meta={
            "emergency_state_id": emergency.id,
            "duration_minutes": payload.duration_minutes,
        },
    )

    db.add(log)

    await db.commit()
    await db.refresh(emergency)

    return emergency


@router.post("/emergency/reset")
async def reset_emergency(
    payload: EmergencyReset,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    target_type = payload.target_type
    display_id = payload.display_id
    group_id = payload.group_id

    complex_id = payload.complex_id or user.complex_id

    if target_type == "display":
        if display_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="display_id is required",
            )

        result = await db.execute(
            select(Display).where(Display.id == display_id)
        )
        display = result.scalar_one_or_none()

        if display is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Display not found",
            )

        _require_same_complex(user, display.complex_id)
        complex_id = display.complex_id

        stmt = select(EmergencyState).where(
            EmergencyState.display_id == display_id,
            EmergencyState.is_active.is_(True),
        )

    elif target_type == "group":
        if group_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="group_id is required",
            )

        result = await db.execute(
            select(DisplayGroup).where(DisplayGroup.id == group_id)
        )
        group = result.scalar_one_or_none()

        if group is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Display group not found",
            )

        _require_same_complex(user, group.complex_id)
        complex_id = group.complex_id

        stmt = select(EmergencyState).where(
            EmergencyState.group_id == group_id,
            EmergencyState.is_active.is_(True),
        )

    elif target_type == "complex":
        if complex_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="User is not linked to complex",
            )

        _require_same_complex(user, complex_id)

        stmt = select(EmergencyState).where(
            EmergencyState.complex_id == complex_id,
            EmergencyState.target_type == "complex",
            EmergencyState.is_active.is_(True),
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid target_type",
        )

    result = await db.execute(stmt)
    emergencies = result.scalars().all()

    now = datetime.now(timezone.utc)

    for emergency in emergencies:
        emergency.is_active = False
        emergency.reset_at = now

    log = EmergencyLog(
        complex_id=complex_id,
        action="reset",
        target_type=target_type,
        target_id=display_id or group_id or complex_id,
        created_by_user_id=user.id,
        meta={
            "reset_count": len(emergencies),
        },
    )

    db.add(log)

    await db.commit()

    return {
        "status": "ok",
        "reset_count": len(emergencies),
    }

@router.post("/content", response_model=ContentItemResponse)
async def create_content_item(
    payload: ContentItemCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    _require_same_complex(user, payload.complex_id)

    item = ContentItem(
        **payload.model_dump(),
        created_by_user_id=user.id,
    )

    db.add(item)
    await db.commit()
    await db.refresh(item)

    return item


@router.get("/content", response_model=list[ContentItemResponse])
async def get_content_items(
    complex_id: int,
    include_ujin: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    _require_same_complex(user, complex_id)

    stmt = select(ContentItem).where(
        ContentItem.complex_id == complex_id,
        ContentItem.is_active.is_(True),
    )

    if not include_ujin:
        stmt = stmt.where(
            ~ContentItem.content_type.in_(
                [
                    "ujin_news",
                    "parking_stats",
                    "storage_stats",
                ]
            )
        )

    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/content/{content_id}", response_model=ContentItemResponse)
async def get_content_item(
    content_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    result = await db.execute(
        select(ContentItem).where(ContentItem.id == content_id)
    )

    item = result.scalar_one_or_none()

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content item not found",
        )

    _require_same_complex(user, item.complex_id)

    return item


@router.patch("/content/{content_id}", response_model=ContentItemResponse)
async def update_content_item(
    content_id: int,
    payload: ContentItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    result = await db.execute(
        select(ContentItem).where(ContentItem.id == content_id)
    )

    item = result.scalar_one_or_none()

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content item not found",
        )

    _require_same_complex(user, item.complex_id)

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)

    await db.commit()
    await db.refresh(item)

    return item


@router.delete("/content/{content_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_content_item(
    content_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_info),
):
    result = await db.execute(
        select(ContentItem).where(ContentItem.id == content_id)
    )

    item = result.scalar_one_or_none()

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content item not found",
        )

    _require_same_complex(user, item.complex_id)

    item.is_active = False
    await db.commit()

    return None

async def _get_display_payload_by_code(
    code: str,
    db: AsyncSession,
) -> dict[str, Any]:
    result = await db.execute(
        select(Display).where(
            Display.code == code,
            Display.is_active.is_(True),
        )
    )
    display = result.scalar_one_or_none()

    if display is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Display not found",
        )

    now = datetime.now(timezone.utc)

    display.is_online = True
    display.last_seen_at = now

    complex_obj = (
        await db.execute(
            select(ResidentialComplex).where(
                ResidentialComplex.id == display.complex_id,
                ResidentialComplex.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()

    building = None
    if display.building_id is not None:
        building = (
            await db.execute(
                select(Building).where(
                    Building.id == display.building_id,
                    Building.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()

    template = None
    if display.current_template_id:
        template = (
            await db.execute(
                select(Template).where(
                    Template.id == display.current_template_id,
                    Template.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()

    content_items = (
        await db.execute(
            select(ContentItem).where(
                ContentItem.complex_id == display.complex_id,
                ContentItem.is_active.is_(True),
                ~ContentItem.content_type.in_(
                    ["ujin_news", "parking_stats", "storage_stats"]
                ),
                or_(
                    ContentItem.publish_from.is_(None),
                    ContentItem.publish_from <= now,
                ),
                or_(
                    ContentItem.publish_to.is_(None),
                    ContentItem.publish_to >= now,
                ),
            )
        )
    ).scalars().all()

    group_ids_result = await db.execute(
        select(display_group_items.c.group_id).where(
            display_group_items.c.display_id == display.id
        )
    )
    group_ids = list(group_ids_result.scalars().all())

    groups = []
    if group_ids:
        groups = (
            await db.execute(
                select(DisplayGroup).where(
                    DisplayGroup.id.in_(group_ids),
                    DisplayGroup.is_active.is_(True),
                )
            )
        ).scalars().all()

    emergency = (
        await db.execute(
            select(EmergencyState)
            .where(
                EmergencyState.complex_id == display.complex_id,
                EmergencyState.is_active.is_(True),
                or_(
                    EmergencyState.display_id == display.id,
                    EmergencyState.target_type == "complex",
                    EmergencyState.group_id.in_(group_ids) if group_ids else False,
                ),
                or_(
                    EmergencyState.expires_at.is_(None),
                    EmergencyState.expires_at >= now,
                ),
            )
            .order_by(EmergencyState.priority.desc())
        )
    ).scalar_one_or_none()

    ujin_data = await _build_ujin_payload_from_db(db, display)

    await db.commit()
    await db.refresh(display)

    return {
        "display": display,
        "residential_complex": complex_obj,
        "building": building,
        "groups": groups,
        "template": template,
        "content_items": content_items,
        "emergency": emergency,
        "ujin_data": ujin_data,
        "generated_at": now,
    }


@router.get("/client/displays/{code}/payload", response_model=DisplayPayload)
async def client_display_payload(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    return await _get_display_payload_by_code(code=code, db=db)


@router.get("/display/{code}/payload", response_model=DisplayPayload)
async def display_payload(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    return await _get_display_payload_by_code(code=code, db=db)