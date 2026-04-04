import os
from pathlib import Path

from fastapi import HTTPException

EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".py": "python",
    ".json": "json",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".md": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    ".sql": "sql",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".r": "r",
    ".R": "r",
    ".lua": "lua",
    ".perl": "perl",
    ".pl": "perl",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".env": "bash",
    ".dockerfile": "dockerfile",
    ".graphql": "graphql",
    ".vue": "html",
    ".svelte": "html",
    ".txt": "plaintext",
    ".log": "plaintext",
    ".csv": "plaintext",
}

MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB

BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg",
    ".mp3", ".wav", ".ogg", ".flac", ".aac",
    ".mp4", ".avi", ".mov", ".mkv", ".webm",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".dat",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
})


def validate_path_safe(path: str) -> None:
    if ".." in path or "\\" in path:
        raise HTTPException(status_code=400, detail="Invalid path: path traversal not allowed")


def validate_name_safe(name: str) -> None:
    if not name or "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid name: contains illegal characters")


def resolve_user_root(base: str, user_id: str) -> Path:
    return Path(base).resolve() / user_id


def get_language(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return EXTENSION_LANGUAGE_MAP.get(ext, "plaintext")


def is_binary(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in BINARY_EXTENSIONS


def is_hidden(name: str) -> bool:
    return name.startswith(".")
