import os
import re
import shutil
from pathlib import Path
from urllib.parse import quote, unquote

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile

from app.config import save_persistent_config, settings
from app.schemas import (
    BaseUrlResponse,
    CreateItemRequest,
    FileContent,
    GraphEdge,
    GraphNode,
    GraphResponse,
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
    save_persistent_config(str(new_path))
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


# ---- Knowledge Graph ----

# Patterns: [text](path.md)  [text](./path.md)  [[wikilink]]  [[wikilink|alias]]
_RE_MD_LINK = re.compile(r'\[(?:[^\]]*)\]\(([^)]+\.md)\)', re.IGNORECASE)
_RE_WIKI_LINK = re.compile(r'\[\[([^|\]]+?)(?:\|[^\]]*?)?\]\]')


def _collect_md_files(root: Path) -> dict[str, Path]:
    """Return {relative_path: absolute_path} for all .md files under root."""
    md_map: dict[str, Path] = {}
    for p in root.rglob("*.md"):
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        md_map[rel] = p
    return md_map


def _resolve_link(link: str, source_rel: str, md_set: set[str]) -> str | None:
    """Resolve a link target to a known md relative path, or None."""
    link = unquote(link).replace("\\", "/")
    # Strip leading ./
    if link.startswith("./"):
        link = link[2:]
    # Try relative to source file's directory
    source_dir = str(Path(source_rel).parent).replace("\\", "/")
    if source_dir == ".":
        candidate = link
    else:
        candidate = f"{source_dir}/{link}"
    if candidate in md_set:
        return candidate
    # Try as absolute (from root)
    if link in md_set:
        return link
    return None


def _resolve_wikilink(name: str, md_set: set[str]) -> str | None:
    """Resolve [[name]] to a known md path by matching filename."""
    target = name.strip().replace("\\", "/")
    if not target.lower().endswith(".md"):
        target += ".md"
    # Exact match
    if target in md_set:
        return target
    # Match by filename anywhere
    for rel in md_set:
        if rel.endswith("/" + target) or rel == target:
            return rel
        # Match without .md extension in the set
        basename = rel.rsplit("/", 1)[-1]
        if basename == target:
            return rel
    return None


@router.get("/graph", response_model=GraphResponse)
async def get_graph(userId: str = Query(...)):
    root = resolve_user_root(settings.FILE_URL, userId)
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
        return GraphResponse(nodes=[], edges=[])

    md_files = _collect_md_files(root)
    md_set = set(md_files.keys())

    nodes = [
        GraphNode(id=rel, name=Path(rel).stem, type="file")
        for rel in sorted(md_set)
    ]

    edges: list[GraphEdge] = []
    seen_edges: set[tuple[str, str]] = set()

    for rel, abs_path in md_files.items():
        try:
            text = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # Standard markdown links [text](path.md)
        for match in _RE_MD_LINK.finditer(text):
            target = _resolve_link(match.group(1), rel, md_set)
            if target and target != rel and (rel, target) not in seen_edges:
                edges.append(GraphEdge(source=rel, target=target))
                seen_edges.add((rel, target))

        # Wiki-style links [[name]]
        for match in _RE_WIKI_LINK.finditer(text):
            target = _resolve_wikilink(match.group(1), md_set)
            if target and target != rel and (rel, target) not in seen_edges:
                edges.append(GraphEdge(source=rel, target=target))
                seen_edges.add((rel, target))

    return GraphResponse(nodes=nodes, edges=edges)


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


@router.post("/upload")
async def upload_file(
    userId: str = Form(...),
    parentPath: str = Form(""),
    file: UploadFile = File(...),
):
    validate_path_safe(parentPath)
    validate_name_safe(file.filename)

    root = resolve_user_root(settings.FILE_URL, userId)
    root.mkdir(parents=True, exist_ok=True)

    parent = (root / parentPath).resolve() if parentPath else root
    if not str(parent).startswith(str(root)):
        raise HTTPException(status_code=400, detail="Invalid path")

    parent.mkdir(parents=True, exist_ok=True)
    target = parent / file.filename

    async with aiofiles.open(target, "wb") as f:
        while chunk := await file.read(1024 * 64):
            await f.write(chunk)

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
