import os
import shutil
from pathlib import Path
from urllib.parse import quote

import aiofiles
from fastapi import APIRouter, HTTPException, Query, Request

from app.config import settings
from app.schemas import (
    BaseUrlResponse,
    CreateItemRequest,
    FileContent,
    RenameItemRequest,
    SaveContentRequest,
    SetBaseUrlRequest,
    TreeNode,
)
from app.utils import (
    MAX_FILE_SIZE,
    get_language,
    is_binary,
    is_hidden,
    resolve_user_root,
    validate_name_safe,
    validate_path_safe,
)

router = APIRouter(prefix="/api/materials", tags=["materials"])


def _build_file_url(request: Request, user_id: str, rel_path: str) -> str:
    """Build an external-accessible URL for a file under /files/{userId}/{path}."""
    safe_path = quote(f"{user_id}/{rel_path}", safe="/")
    return str(request.base_url).rstrip("/") + f"/files/{safe_path}"


@router.get("/baseurl", response_model=BaseUrlResponse)
async def get_base_url():
    return BaseUrlResponse(baseUrl=settings.FILE_URL)


@router.put("/baseurl", response_model=BaseUrlResponse)
async def set_base_url(body: SetBaseUrlRequest):
    new_path = Path(body.baseUrl).resolve()
    new_path.mkdir(parents=True, exist_ok=True)
    settings.FILE_URL = str(new_path)
    # Persist to .env
    env_path = Path(__file__).resolve().parent.parent / ".env"
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    updated = False
    for i, line in enumerate(lines):
        if line.startswith("FILE_URL="):
            lines[i] = f"FILE_URL={new_path}"
            updated = True
            break
    if not updated:
        lines.append(f"FILE_URL={new_path}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return BaseUrlResponse(baseUrl=settings.FILE_URL)


def _build_tree(base: Path, rel: str = "") -> list[TreeNode]:
    current = base / rel if rel else base
    dirs: list[TreeNode] = []
    files: list[TreeNode] = []

    for entry in sorted(current.iterdir(), key=lambda e: e.name.lower()):
        if is_hidden(entry.name):
            continue
        entry_rel = f"{rel}/{entry.name}".lstrip("/") if rel else entry.name
        if entry.is_dir():
            children = _build_tree(base, entry_rel)
            dirs.append(TreeNode(name=entry.name, path=entry_rel, type="directory", children=children))
        else:
            files.append(TreeNode(name=entry.name, path=entry_rel, type="file", children=None))

    return dirs + files


@router.get("/tree", response_model=list[TreeNode])
async def get_tree(userId: str = Query(...)):
    root = resolve_user_root(settings.FILE_URL, userId)
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
        return []
    return _build_tree(root)


@router.get("/content", response_model=FileContent)
async def get_content(request: Request, userId: str = Query(...), path: str = Query(...)):
    validate_path_safe(path)
    root = resolve_user_root(settings.FILE_URL, userId)
    file_path = (root / path).resolve()

    # Ensure resolved path is under user root
    if not str(file_path).startswith(str(root)):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    name = file_path.name
    size = file_path.stat().st_size

    if is_binary(name):
        file_url = _build_file_url(request, userId, path)
        return FileContent(
            path=path, name=name, content=file_url,
            language=get_language(name), size=size,
        )

    if size > MAX_FILE_SIZE:
        file_url = _build_file_url(request, userId, path)
        return FileContent(
            path=path, name=name, content=file_url,
            language=get_language(name), size=size,
        )

    async with aiofiles.open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = await f.read()

    return FileContent(
        path=path, name=name, content=content,
        language=get_language(name), size=size,
    )


@router.put("/content")
async def save_content(body: SaveContentRequest):
    validate_path_safe(body.path)
    root = resolve_user_root(settings.FILE_URL, body.userId)
    file_path = (root / body.path).resolve()

    if not str(file_path).startswith(str(root)):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    if is_binary(file_path.name):
        raise HTTPException(status_code=400, detail="Cannot edit binary files")

    async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
        await f.write(body.content)

    return None


@router.post("")
async def create_item(body: CreateItemRequest):
    validate_path_safe(body.parentPath)
    validate_name_safe(body.name)

    root = resolve_user_root(settings.FILE_URL, body.userId)
    root.mkdir(parents=True, exist_ok=True)

    parent = (root / body.parentPath).resolve() if body.parentPath else root
    if not str(parent).startswith(str(root)):
        raise HTTPException(status_code=400, detail="Invalid path")

    target = parent / body.name

    if target.exists():
        raise HTTPException(status_code=409, detail="Item already exists")

    if body.type == "directory":
        target.mkdir(parents=True, exist_ok=True)
    else:
        parent.mkdir(parents=True, exist_ok=True)
        target.touch()

    return None


@router.put("/rename")
async def rename_item(body: RenameItemRequest):
    validate_path_safe(body.path)
    validate_name_safe(body.newName)

    root = resolve_user_root(settings.FILE_URL, body.userId)
    source = (root / body.path).resolve()

    if not str(source).startswith(str(root)):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not source.exists():
        raise HTTPException(status_code=404, detail="Item not found")

    destination = source.parent / body.newName

    if destination.exists():
        raise HTTPException(status_code=409, detail="An item with this name already exists")

    source.rename(destination)
    return None


@router.delete("")
async def delete_item(userId: str = Query(...), path: str = Query(...)):
    validate_path_safe(path)
    root = resolve_user_root(settings.FILE_URL, userId)
    target = (root / path).resolve()

    if not str(target).startswith(str(root)):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists():
        raise HTTPException(status_code=404, detail="Item not found")

    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()

    return None
